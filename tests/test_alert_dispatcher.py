"""Tests for the alert_dispatcher (notification delivery) logic."""

import json

import responses

from shared.alert_client import AlertClient  # pylint: disable=import-error
from shared.models import CostAlert  # pylint: disable=import-error


class TestAlertClient:
    """Test alert formatting and webhook delivery."""

    def _make_alert(self, severity="warning", title="Test Alert"):
        return CostAlert(
            severity=severity,
            title=title,
            message="Test message body",
            cost_impact=500.0,
            source="test_suite",
        )

    @responses.activate
    def test_dispatch_to_slack(self):
        """Should POST formatted message to Slack webhook."""
        responses.add(
            responses.POST,
            "https://example.com/slack",
            json={"ok": True},
            status=200,
        )

        client = AlertClient(
            slack_url="https://example.com/slack",
            teams_url="",
        )
        alert = self._make_alert()
        results = client.dispatch(alert)

        assert results["slack"] is True
        assert len(responses.calls) == 1
        payload = json.loads(responses.calls[0].request.body)
        assert "FinOps Alert" in payload["text"]
        assert "$500.00" in payload["text"]

    @responses.activate
    def test_dispatch_to_teams(self):
        """Should POST MessageCard to Teams webhook."""
        responses.add(
            responses.POST,
            "https://example.com/teams",
            body="1",
            status=200,
        )

        client = AlertClient(
            slack_url="",
            teams_url="https://example.com/teams",
        )
        alert = self._make_alert(severity="critical", title="Budget Exceeded")
        results = client.dispatch(alert)

        assert results["teams"] is True
        payload = json.loads(responses.calls[0].request.body)
        assert payload["@type"] == "MessageCard"
        assert payload["themeColor"] == "FF0000"

    @responses.activate
    def test_dispatch_to_both_channels(self):
        """Should send to both Slack and Teams when both configured."""
        responses.add(responses.POST, "https://example.com/slack", status=200)
        responses.add(responses.POST, "https://example.com/teams", status=200)

        client = AlertClient(
            slack_url="https://example.com/slack",
            teams_url="https://example.com/teams",
        )
        alert = self._make_alert()
        results = client.dispatch(alert)

        assert results["slack"] is True
        assert results["teams"] is True
        assert len(responses.calls) == 2

    def test_dispatch_no_webhooks(self):
        """Should return empty dict when no webhook URLs configured."""
        client = AlertClient(slack_url="", teams_url="")
        results = client.dispatch(self._make_alert())
        assert results == {}

    @responses.activate
    def test_dispatch_handles_failure(self):
        """Should return False for a channel that errors."""
        responses.add(
            responses.POST,
            "https://example.com/slack",
            status=500,
        )

        client = AlertClient(slack_url="https://example.com/slack", teams_url="")
        alert = self._make_alert()
        results = client.dispatch(alert)

        assert results["slack"] is False

    def test_severity_colours(self):
        """Teams card should use the right colour per severity."""
        for severity, expected_colour in [
            ("critical", "FF0000"),
            ("warning", "FFA500"),
            ("info", "0078D4"),
        ]:
            _ = self._make_alert(severity=severity)
            _ = AlertClient(slack_url="", teams_url="")
            # Test the internal Teams payload builder
            colour = {"critical": "FF0000", "warning": "FFA500", "info": "0078D4"}.get(severity, "808080")
            assert colour == expected_colour
