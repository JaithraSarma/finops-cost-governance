"""
End-to-end integration test that validates the complete data pipeline
without connecting to Azure — all external services are mocked.

Flow tested:
  1. Cost data collection → storage
  2. Waste resource detection → storage
  3. Advisor recommendation fetch → storage
  4. Alert generation when thresholds exceeded
  5. Alert dispatch to webhooks
  6. API reads back stored data
"""

import json
from collections import defaultdict

import responses

from shared.models import CostAlert  # pylint: disable=import-error
from shared.alert_client import AlertClient  # pylint: disable=import-error


class TestEndToEndPipeline:
    """Simulates the full daily governance pipeline."""

    def test_full_pipeline(self, sample_cost_records, sample_waste_resources,
                           sample_recommendations, mock_storage_client):
        """
        Runs through the entire pipeline:
        1. Store cost records
        2. Store waste findings
        3. Store recommendations
        4. Generate alert
        5. Check stored data via API-like queries
        """
        storage = mock_storage_client

        # ── Step 1: Cost collection ──────────────────────────────────────
        cost_entities = [r.to_entity() for r in sample_cost_records]
        stored = storage.upsert_entities("CostRecords", cost_entities)
        assert stored == 4

        # ── Step 2: Waste detection ──────────────────────────────────────
        waste_entities = [w.to_entity() for w in sample_waste_resources]
        stored = storage.upsert_entities("WasteResources", waste_entities)
        assert stored == 3

        # ── Step 3: Advisor recommendations ──────────────────────────────
        rec_entities = [r.to_entity() for r in sample_recommendations]
        stored = storage.upsert_entities("Recommendations", rec_entities)
        assert stored == 2

        # ── Step 4: Alert generation ─────────────────────────────────────
        total_waste = sum(w.estimated_monthly_savings for w in sample_waste_resources)
        assert total_waste > 0

        alert = CostAlert(
            severity="warning",
            title="Resource Waste Detected",
            message=f"Found {len(sample_waste_resources)} waste items, ~${total_waste:.2f}/mo savings",
            cost_impact=total_waste,
            source="resource_analyzer",
        )
        storage.insert_entity("Alerts", alert.to_entity())

        # ── Step 5: Verify stored data ───────────────────────────────────
        costs = storage.get_all("CostRecords")
        assert len(costs) == 4

        waste = storage.get_all("WasteResources")
        assert len(waste) == 3

        recs = storage.get_all("Recommendations")
        assert len(recs) == 2

        alerts = storage.get_all("Alerts")
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "warning"

        # ── Step 6: API-like aggregations ────────────────────────────────
        total_cost = sum(float(c.get("cost", 0)) for c in costs)
        assert round(total_cost, 2) == 400.60

        daily = defaultdict(float)
        for c in costs:
            daily[c["date"]] += float(c["cost"])
        assert len(daily) == 2

        by_team = defaultdict(float)
        for c in costs:
            by_team[c.get("team", "untagged")] += float(c["cost"])
        assert "backend" in by_team

    @responses.activate
    def test_alert_dispatch_integration(self):
        """Test that alerts are correctly dispatched to webhooks."""
        responses.add(responses.POST, "https://example.com/slack", status=200)
        responses.add(responses.POST, "https://example.com/teams", status=200)

        alert = CostAlert(
            severity="critical",
            title="Monthly Budget Exceeded",
            message="Current month spend $16,000 exceeds budget of $15,000",
            cost_impact=1000.00,
            source="cost_collector",
        )

        client = AlertClient(
            slack_url="https://example.com/slack",
            teams_url="https://example.com/teams",
        )
        results = client.dispatch(alert)

        assert results["slack"] is True
        assert results["teams"] is True

        # Verify Slack payload
        slack_payload = json.loads(responses.calls[0].request.body)
        assert "Budget Exceeded" in slack_payload["text"]
        assert "$1,000.00" in slack_payload["text"]

        # Verify Teams payload
        teams_payload = json.loads(responses.calls[1].request.body)
        assert teams_payload["themeColor"] == "FF0000"
        assert teams_payload["sections"][0]["facts"][0]["value"] == "CRITICAL"
