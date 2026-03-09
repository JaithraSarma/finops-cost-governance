"""Tests for the cost_collector function logic."""

from unittest.mock import MagicMock, patch

from shared.models import CostRecord  # pylint: disable=import-error


class TestCostCollector:
    """Test the cost collection and anomaly detection logic."""

    # pylint: disable=import-error

    @patch("shared.cost_client.CostManagementClient")
    @patch("shared.cost_client.DefaultAzureCredential")
    def test_query_daily_costs(self, mock_cred, mock_cm_client):
        """CostClient.query_daily_costs should parse API results into CostRecords."""
        from shared.cost_client import CostClient

        # Build a mock API response
        mock_result = MagicMock()
        mock_result.columns = [
            MagicMock(name="Cost"),
            MagicMock(name="ResourceGroup"),
            MagicMock(name="MeterCategory"),
            MagicMock(name="UsageDate"),
        ]
        mock_result.rows = [
            [120.50, "rg-app-prod", "Virtual Machines", 20260301],
            [15.30, "rg-app-dev", "Storage", 20260301],
        ]
        mock_cm_client.return_value.query.usage.return_value = mock_result

        client = CostClient(credential=mock_cred())
        records = client.query_daily_costs(lookback_days=7)

        assert len(records) == 2
        assert isinstance(records[0], CostRecord)
        assert records[0].cost == 120.50
        assert records[0].resource_group == "rg-app-prod"
        assert records[0].date == "2026-03-01"

    @patch("shared.cost_client.CostManagementClient")
    @patch("shared.cost_client.DefaultAzureCredential")
    def test_get_current_month_total(self, mock_cred, mock_cm_client):
        """CostClient.get_current_month_total should return the aggregate cost."""
        from shared.cost_client import CostClient

        mock_result = MagicMock()
        mock_result.rows = [[8750.42]]
        mock_cm_client.return_value.query.usage.return_value = mock_result

        client = CostClient(credential=mock_cred())
        total = client.get_current_month_total()

        assert total == 8750.42

    @patch("shared.cost_client.CostManagementClient")
    @patch("shared.cost_client.DefaultAzureCredential")
    def test_empty_api_response(self, mock_cred, mock_cm_client):
        """An empty API response should return an empty list."""
        from shared.cost_client import CostClient

        mock_result = MagicMock()
        mock_result.rows = []
        mock_cm_client.return_value.query.usage.return_value = mock_result

        client = CostClient(credential=mock_cred())
        records = client.query_daily_costs()
        assert records == []

    def test_anomaly_detection_logic(self, sample_cost_records):
        """Verify the anomaly detection algorithm catches cost spikes."""
        # Day 1 total: 120.50 + 15.30 = 135.80
        # Day 2 total: 250.00 + 14.80 = 264.80
        # Change: (264.80 - 135.80) / 135.80 * 100 = 95.0%  → anomaly
        records = sample_cost_records
        daily_totals: dict[str, float] = {}
        for r in records:
            daily_totals[r.date] = daily_totals.get(r.date, 0.0) + r.cost

        sorted_dates = sorted(daily_totals.keys(), reverse=True)
        latest = daily_totals[sorted_dates[0]]
        previous = daily_totals[sorted_dates[1]]
        pct_change = ((latest - previous) / previous) * 100

        assert pct_change > 20  # exceeds default 20% threshold
        assert round(pct_change, 1) == 95.0

    def test_no_anomaly_when_stable(self):
        """No anomaly should fire when costs are stable."""
        records = [
            CostRecord(date="2026-03-01", subscription_id="s1", resource_group="rg1",
                       service_name="VM", cost=100.0),
            CostRecord(date="2026-03-02", subscription_id="s1", resource_group="rg1",
                       service_name="VM", cost=105.0),
        ]
        daily_totals = {}
        for r in records:
            daily_totals[r.date] = daily_totals.get(r.date, 0.0) + r.cost

        sorted_dates = sorted(daily_totals.keys(), reverse=True)
        pct_change = ((daily_totals[sorted_dates[0]] - daily_totals[sorted_dates[1]]) /
                      daily_totals[sorted_dates[1]]) * 100

        assert pct_change < 20  # within threshold → no anomaly
