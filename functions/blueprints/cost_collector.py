"""
cost_collector blueprint — Timer-triggered Azure Function

Runs daily at 06:00 UTC to:
  1. Query Azure Cost Management API for the last 30 days of costs
  2. Store aggregated records in Azure Table Storage
  3. Check if daily spend exceeds the configured budget threshold
  4. If threshold breached, enqueue an alert for the alert_dispatcher
"""

import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from shared.config import settings
from shared.cost_client import CostClient
from shared.models import CostAlert
from shared.storage_client import StorageClient

logger = logging.getLogger(__name__)
bp = func.Blueprint()


@bp.timer_trigger(
    schedule="0 0 6 * * *",      # Every day at 06:00 UTC
    arg_name="timer",
    run_on_startup=False,
)
@bp.queue_output(
    arg_name="alertqueue",
    queue_name="cost-alerts",
    connection="STORAGE_CONNECTION_STRING",
)
def cost_collector(timer: func.TimerRequest, alertqueue: func.Out[str]) -> None:
    """Collect daily cost data and check budget thresholds."""
    logger.info("cost_collector triggered at %s", datetime.now(timezone.utc).isoformat())

    if timer.past_due:
        logger.warning("Timer is past due — running catch-up execution")

    # 1. Fetch cost data
    cost_client = CostClient()
    records = cost_client.query_daily_costs(lookback_days=settings.COST_LOOKBACK_DAYS)
    logger.info("Retrieved %d cost records", len(records))

    # 2. Persist to Table Storage
    storage = StorageClient()
    entities = [r.to_entity() for r in records]
    stored = storage.upsert_entities(settings.COST_TABLE_NAME, entities)
    logger.info("Stored %d cost records", stored)

    # 3. Check current-month total against budget
    monthly_total = cost_client.get_current_month_total()
    logger.info("Current month total: $%.2f (budget: $%.2f)", monthly_total, settings.MONTHLY_BUDGET_LIMIT)

    if monthly_total > settings.MONTHLY_BUDGET_LIMIT:
        alert = CostAlert(
            severity="critical",
            title="Monthly Budget Exceeded",
            message=(
                f"Current month spend ${monthly_total:,.2f} has exceeded "
                f"the budget of ${settings.MONTHLY_BUDGET_LIMIT:,.2f}."
            ),
            cost_impact=monthly_total - settings.MONTHLY_BUDGET_LIMIT,
            source="cost_collector",
        )
        alertqueue.set(json.dumps(alert.to_dict()))
        logger.warning("Budget exceeded — alert enqueued")

    # 4. Check for daily anomalies (> threshold % increase from previous day)
    _check_daily_anomaly(records, alertqueue)

    logger.info("cost_collector completed successfully")


def _check_daily_anomaly(records, alertqueue: func.Out[str]) -> None:
    """Compare the two most recent days to detect cost spikes."""
    if len(records) < 2:
        return

    # Group costs by date
    daily_totals: dict[str, float] = {}
    for r in records:
        daily_totals[r.date] = daily_totals.get(r.date, 0.0) + r.cost

    sorted_dates = sorted(daily_totals.keys(), reverse=True)
    if len(sorted_dates) < 2:
        return

    latest_cost = daily_totals[sorted_dates[0]]
    previous_cost = daily_totals[sorted_dates[1]]

    if previous_cost == 0:
        return

    pct_change = ((latest_cost - previous_cost) / previous_cost) * 100

    if pct_change > settings.COST_ANOMALY_THRESHOLD_PERCENT:
        alert = CostAlert(
            severity="warning",
            title="Daily Cost Anomaly Detected",
            message=(
                f"Daily cost spiked by {pct_change:.1f}% "
                f"(${previous_cost:,.2f} → ${latest_cost:,.2f}). "
                f"Threshold: {settings.COST_ANOMALY_THRESHOLD_PERCENT}%."
            ),
            cost_impact=latest_cost - previous_cost,
            source="cost_collector",
        )
        alertqueue.set(json.dumps(alert.to_dict()))
        logger.warning("Cost anomaly detected — alert enqueued")
