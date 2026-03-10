"""
Alert dispatcher client.

Sends formatted notifications to Slack and Microsoft Teams via
Logic Apps HTTP-trigger webhook URLs.
"""

from __future__ import annotations

import json
import logging

import requests

from shared.config import settings
from shared.models import CostAlert

logger = logging.getLogger(__name__)

# Timeout for outgoing HTTP calls (seconds)
_WEBHOOK_TIMEOUT = 15


class AlertClient:
    """Dispatches CostAlert objects to configured notification channels."""

    def __init__(
        self,
        slack_url: str | None = None,
        teams_url: str | None = None,
    ):
        self._slack_url = slack_url or settings.SLACK_WEBHOOK_URL
        self._teams_url = teams_url or settings.TEAMS_WEBHOOK_URL

    def dispatch(self, alert: CostAlert) -> dict[str, bool]:
        """Send alert to all configured channels. Returns delivery status."""
        results: dict[str, bool] = {}
        if self._slack_url:
            results["slack"] = self._send_slack(alert)
        if self._teams_url:
            results["teams"] = self._send_teams(alert)
        if not results:
            logger.warning("No webhook URLs configured — alert not dispatched")
        return results

    def _send_slack(self, alert: CostAlert) -> bool:
        """Format and POST alert to Slack-style Logic App webhook."""
        severity_emoji = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(
            alert.severity, "⚪"
        )
        payload = {
            "text": (
                f"{severity_emoji} *FinOps Alert — {alert.title}*\n"
                f"Severity: `{alert.severity}`\n"
                f"Source: `{alert.source}`\n"
                f"Cost Impact: `${alert.cost_impact:,.2f}`\n\n"
                f"{alert.message}"
            ),
        }
        return self._post(self._slack_url, payload, "Slack")

    def _send_teams(self, alert: CostAlert) -> bool:
        """Format and POST alert to Teams-style Logic App webhook."""
        colour = {"critical": "FF0000", "warning": "FFA500", "info": "0078D4"}.get(
            alert.severity, "808080"
        )
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": colour,
            "summary": f"FinOps Alert — {alert.title}",
            "sections": [
                {
                    "activityTitle": f"FinOps Alert — {alert.title}",
                    "facts": [
                        {"name": "Severity", "value": alert.severity.upper()},
                        {"name": "Source", "value": alert.source},
                        {"name": "Cost Impact", "value": f"${alert.cost_impact:,.2f}"},
                    ],
                    "text": alert.message,
                    "markdown": True,
                }
            ],
        }
        return self._post(self._teams_url, payload, "Teams")

    @staticmethod
    def _post(url: str, payload: dict, channel: str) -> bool:
        """HTTP POST with error handling."""
        try:
            resp = requests.post(
                url,
                data=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=_WEBHOOK_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info("Alert dispatched to %s (status=%d)", channel, resp.status_code)
            return True
        except requests.RequestException:
            logger.exception("Failed to dispatch alert to %s", channel)
            return False
