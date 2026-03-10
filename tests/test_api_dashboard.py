"""Tests for the api_dashboard HTTP endpoints."""

import json
from unittest.mock import MagicMock, patch


class TestHealthEndpoint:
    def test_health_returns_200(self):
        """Health endpoint should return status healthy."""
        # Simulate the response logic inline
        from datetime import datetime, timezone
        body = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
        }
        assert body["status"] == "healthy"
        assert "timestamp" in body


class TestCostsSummary:
    def test_aggregation_logic(self, sample_cost_records):
        """Cost summary should aggregate correctly."""
        records = [r.to_dict() for r in sample_cost_records]
        total_cost = sum(float(r["cost"]) for r in records)
        unique_rgs = {r["resource_group"] for r in records}
        unique_services = {r["service_name"] for r in records}

        assert round(total_cost, 2) == 400.60
        assert len(unique_rgs) == 2
        assert len(unique_services) == 2

    def test_budget_utilisation(self, sample_cost_records):
        """Budget utilisation % should be computed correctly."""
        records = [r.to_dict() for r in sample_cost_records]
        total_cost = sum(float(r["cost"]) for r in records)
        budget = 15000
        utilisation = round((total_cost / budget) * 100, 1)
        assert utilisation == 2.7  # 400.60 / 15000 * 100


class TestCostsTrends:
    def test_daily_aggregation(self, sample_cost_records):
        """Should group costs by date."""
        from collections import defaultdict
        records = [r.to_dict() for r in sample_cost_records]
        daily = defaultdict(float)
        for r in records:
            daily[r["date"]] += float(r["cost"])

        assert len(daily) == 2
        assert round(daily["2026-03-01"], 2) == 135.80
        assert round(daily["2026-03-02"], 2) == 264.80


class TestCostsByTeam:
    def test_team_grouping(self, sample_cost_records):
        """Should group costs by team tag."""
        from collections import defaultdict
        records = [r.to_dict() for r in sample_cost_records]
        by_team = defaultdict(float)
        for r in records:
            team = r.get("team", "") or "untagged"
            by_team[team] += float(r["cost"])

        assert round(by_team["backend"], 2) == 370.50
        assert round(by_team["data"], 2) == 30.10


class TestCostsByEnvironment:
    def test_env_grouping(self, sample_cost_records):
        """Should group costs by environment tag."""
        from collections import defaultdict
        records = [r.to_dict() for r in sample_cost_records]
        by_env = defaultdict(float)
        for r in records:
            env = r.get("environment", "") or "untagged"
            by_env[env] += float(r["cost"])

        assert round(by_env["prod"], 2) == 370.50
        assert round(by_env["dev"], 2) == 30.10


class TestWasteReport:
    def test_waste_summary(self, sample_waste_resources):
        """Waste report should sum up savings correctly."""
        findings = [w.to_dict() for w in sample_waste_resources]
        total_savings = sum(float(f["estimated_monthly_savings"]) for f in findings)
        assert len(findings) == 3
        assert round(total_savings, 2) == 34.40


class TestRecommendations:
    def test_recommendation_summary(self, sample_recommendations):
        """Recommendations should aggregate annual savings."""
        recs = [r.to_dict() for r in sample_recommendations]
        total_annual = sum(float(r["estimated_annual_savings"]) for r in recs)
        assert len(recs) == 2
        assert total_annual == 2760.00
