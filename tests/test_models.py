"""Tests for the data models."""

import json
from shared.models import CostRecord, WasteResource, AdvisorRecommendation, CostAlert  # pylint: disable=import-error


class TestCostRecord:
    def test_create_record(self):
        record = CostRecord(
            date="2026-03-01",
            subscription_id="sub-001",
            resource_group="rg-dev",
            service_name="Virtual Machines",
            cost=123.45,
        )
        assert record.cost == 123.45
        assert record.currency == "USD"
        assert record.partition_key == "sub-001"
        assert "2026-03-01" in record.row_key

    def test_to_entity(self):
        record = CostRecord(
            date="2026-03-01",
            subscription_id="sub-001",
            resource_group="rg-dev",
            service_name="Storage",
            cost=10.00,
        )
        entity = record.to_entity()
        assert entity["PartitionKey"] == "sub-001"
        assert "RowKey" in entity
        assert entity["cost"] == 10.00

    def test_to_dict(self):
        record = CostRecord(
            date="2026-03-01",
            subscription_id="sub-001",
            resource_group="rg-dev",
            service_name="Storage",
            cost=10.00,
        )
        d = record.to_dict()
        assert d["date"] == "2026-03-01"
        assert d["service_name"] == "Storage"

    def test_serialisable_to_json(self):
        record = CostRecord(
            date="2026-03-01",
            subscription_id="sub-001",
            resource_group="rg-dev",
            service_name="Storage",
            cost=10.00,
        )
        result = json.dumps(record.to_dict())
        assert '"cost": 10.0' in result


class TestWasteResource:
    def test_create_waste(self):
        waste = WasteResource(
            resource_id="/subs/s1/rg/rg1/providers/Microsoft.Compute/disks/d1",
            resource_type="Microsoft.Compute/disks",
            resource_name="d1",
            resource_group="rg1",
            subscription_id="s1",
            waste_type="unattached_disk",
            estimated_monthly_savings=5.0,
        )
        assert waste.waste_type == "unattached_disk"
        assert waste.partition_key == "s1"

    def test_to_entity(self):
        waste = WasteResource(
            resource_id="/subs/s1/rg/rg1/providers/Microsoft.Compute/disks/d1",
            resource_type="Microsoft.Compute/disks",
            resource_name="d1",
            resource_group="rg1",
            subscription_id="s1",
            waste_type="unattached_disk",
            estimated_monthly_savings=5.0,
        )
        entity = waste.to_entity()
        assert "PartitionKey" in entity
        assert "RowKey" in entity
        assert "unattached_disk" in entity["RowKey"]


class TestAdvisorRecommendation:
    def test_create_recommendation(self):
        rec = AdvisorRecommendation(
            recommendation_id="rec-001",
            category="Cost",
            impact="High",
            impacted_resource="vm-01",
            impacted_resource_type="Microsoft.Compute/virtualMachines",
            description="Right-size VM",
            estimated_annual_savings=2400.0,
            subscription_id="s1",
        )
        assert rec.impact == "High"
        assert rec.estimated_annual_savings == 2400.0
        assert rec.row_key == "rec-001"

    def test_to_entity(self):
        rec = AdvisorRecommendation(
            recommendation_id="rec-002",
            category="Cost",
            impact="Medium",
            impacted_resource="disk-01",
            impacted_resource_type="Microsoft.Compute/disks",
            description="Switch disk tier",
            estimated_annual_savings=360.0,
            subscription_id="s1",
        )
        entity = rec.to_entity()
        assert entity["RowKey"] == "rec-002"


class TestCostAlert:
    def test_create_alert(self):
        alert = CostAlert(
            severity="critical",
            title="Budget Exceeded",
            message="Spend is $16000, budget is $15000",
            cost_impact=1000.0,
            source="cost_collector",
        )
        assert alert.severity == "critical"
        assert alert.partition_key == "critical"

    def test_to_dict(self):
        alert = CostAlert(
            severity="warning",
            title="Anomaly",
            message="Spike detected",
            cost_impact=200.0,
            source="cost_collector",
        )
        d = alert.to_dict()
        assert d["severity"] == "warning"
        assert d["title"] == "Anomaly"

    def test_json_serialisable(self):
        alert = CostAlert(
            severity="info",
            title="Test",
            message="Test message",
        )
        result = json.dumps(alert.to_dict())
        assert '"severity": "info"' in result
