"""
resource_analyzer blueprint — Timer-triggered Azure Function

Runs daily at 07:00 UTC to scan the subscription for wasted resources:
  - Unattached managed disks
  - Oversized / under-utilised VMs
  - Idle load balancers
  - Unused public IP addresses

Findings are stored in Azure Table Storage and an alert is enqueued
if total potential savings exceed the configured threshold.
"""

import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from shared.config import settings
from shared.models import CostAlert
from shared.resource_client import ResourceAnalyzer
from shared.storage_client import StorageClient

logger = logging.getLogger(__name__)
bp = func.Blueprint()


@bp.timer_trigger(
    schedule="0 0 7 * * *",      # Every day at 07:00 UTC
    arg_name="timer",
    run_on_startup=False,
)
@bp.queue_output(
    arg_name="alertqueue",
    queue_name="cost-alerts",
    connection="STORAGE_CONNECTION_STRING",
)
def resource_analyzer(timer: func.TimerRequest, alertqueue: func.Out[str]) -> None:
    """Scan for idle / underutilised resources and report waste."""
    logger.info("resource_analyzer triggered at %s", datetime.now(timezone.utc).isoformat())

    # 1. Run all waste detection checks
    analyzer = ResourceAnalyzer()
    findings = analyzer.scan_all()
    logger.info("Detected %d waste findings", len(findings))

    # 2. Persist findings to Table Storage
    storage = StorageClient()
    entities = [f.to_entity() for f in findings]
    stored = storage.upsert_entities(settings.WASTE_TABLE_NAME, entities)
    logger.info("Stored %d waste findings", stored)

    # 3. Calculate total potential savings
    total_savings = sum(f.estimated_monthly_savings for f in findings)
    logger.info("Total estimated monthly savings: $%.2f", total_savings)

    # 4. Generate summary alert if savings exceed threshold
    if total_savings >= settings.WASTE_ALERT_MIN_SAVINGS:
        # Build a breakdown by waste type
        breakdown: dict[str, dict] = {}
        for f in findings:
            entry = breakdown.setdefault(f.waste_type, {"count": 0, "savings": 0.0})
            entry["count"] += 1
            entry["savings"] += f.estimated_monthly_savings

        breakdown_lines = "\n".join(
            f"  • {wtype.replace('_', ' ').title()}: "
            f"{info['count']} resource(s), ~${info['savings']:,.2f}/mo"
            for wtype, info in sorted(breakdown.items(), key=lambda x: -x[1]["savings"])
        )

        alert = CostAlert(
            severity="warning" if total_savings < 500 else "critical",
            title="Resource Waste Detected",
            message=(
                f"Found {len(findings)} idle/underutilised resource(s) "
                f"with ~${total_savings:,.2f}/mo in potential savings.\n\n"
                f"Breakdown:\n{breakdown_lines}"
            ),
            cost_impact=total_savings,
            source="resource_analyzer",
        )
        alertqueue.set(json.dumps(alert.to_dict()))
        logger.info("Waste alert enqueued")

    logger.info("resource_analyzer completed successfully")
