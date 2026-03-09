"""
recommendation_fetcher blueprint — Timer-triggered Azure Function

Runs daily at 08:00 UTC to pull cost-optimization recommendations
from Azure Advisor and persist them in Table Storage.
"""

import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from shared.advisor_client import AdvisorClient
from shared.config import settings
from shared.models import CostAlert
from shared.storage_client import StorageClient

logger = logging.getLogger(__name__)
bp = func.Blueprint()


@bp.timer_trigger(
    schedule="0 0 8 * * *",      # Every day at 08:00 UTC
    arg_name="timer",
    run_on_startup=False,
)
@bp.queue_output(
    arg_name="alertqueue",
    queue_name="cost-alerts",
    connection="STORAGE_CONNECTION_STRING",
)
def recommendation_fetcher(timer: func.TimerRequest, alertqueue: func.Out[str]) -> None:
    """Fetch Azure Advisor cost recommendations and persist them."""
    _ = timer  # required by Azure Functions binding
    logger.info("recommendation_fetcher triggered at %s", datetime.now(timezone.utc).isoformat())

    # 1. Fetch recommendations from Azure Advisor
    advisor = AdvisorClient()
    recommendations = advisor.get_cost_recommendations()
    logger.info("Retrieved %d cost recommendations", len(recommendations))

    # 2. Store in Table Storage
    storage = StorageClient()
    entities = [r.to_entity() for r in recommendations]
    stored = storage.upsert_entities(settings.RECOMMENDATIONS_TABLE_NAME, entities)
    logger.info("Stored %d recommendations", stored)

    # 3. Summarise high-impact recommendations
    high_impact = [r for r in recommendations if r.impact == "High"]
    total_annual_savings = sum(r.estimated_annual_savings for r in recommendations)

    if high_impact:
        detail_lines = "\n".join(
            f"  • [{r.impact}] {r.description} — "
            f"~${r.estimated_annual_savings:,.2f}/yr ({r.impacted_resource})"
            for r in sorted(high_impact, key=lambda x: -x.estimated_annual_savings)[:10]
        )

        alert = CostAlert(
            severity="warning",
            title=f"{len(high_impact)} High-Impact Cost Recommendations",
            message=(
                f"Azure Advisor found {len(recommendations)} cost recommendations "
                f"with ~${total_annual_savings:,.2f}/yr in potential savings.\n\n"
                f"Top high-impact items:\n{detail_lines}"
            ),
            cost_impact=total_annual_savings,
            source="recommendation_fetcher",
        )
        alertqueue.set(json.dumps(alert.to_dict()))
        logger.info("Advisor alert enqueued (%d high-impact)", len(high_impact))

    logger.info("recommendation_fetcher completed successfully")
