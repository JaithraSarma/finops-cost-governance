"""
alert_dispatcher blueprint — Queue-triggered Azure Function

Processes alert messages from the 'cost-alerts' queue and dispatches
them to Slack and Microsoft Teams via Logic Apps webhook URLs.
Also persists every alert in Table Storage for audit purposes.
"""

import json
import logging

import azure.functions as func

from shared.alert_client import AlertClient
from shared.config import settings
from shared.models import CostAlert
from shared.storage_client import StorageClient

logger = logging.getLogger(__name__)
bp = func.Blueprint()


@bp.queue_trigger(
    arg_name="msg",
    queue_name="cost-alerts",
    connection="STORAGE_CONNECTION_STRING",
)
def alert_dispatcher(msg: func.QueueMessage) -> None:
    """Receive an alert from the queue and dispatch to notification channels."""
    raw = msg.get_body().decode("utf-8")
    logger.info("alert_dispatcher received message: %s", raw[:200])

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in queue message")
        return

    alert = CostAlert(
        severity=data.get("severity", "info"),
        title=data.get("title", "Unknown Alert"),
        message=data.get("message", ""),
        cost_impact=float(data.get("cost_impact", 0)),
        source=data.get("source", "unknown"),
        alert_id=data.get("alert_id", ""),
        created_at=data.get("created_at", ""),
    )

    # 1. Persist alert to Table Storage for audit trail
    storage = StorageClient()
    storage.insert_entity(settings.ALERTS_TABLE_NAME, alert.to_entity())
    logger.info("Alert persisted: %s", alert.title)

    # 2. Dispatch to Slack / Teams
    client = AlertClient()
    results = client.dispatch(alert)

    for channel, success in results.items():
        if success:
            logger.info("Alert sent to %s successfully", channel)
        else:
            logger.error("Failed to send alert to %s", channel)
