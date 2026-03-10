"""
Pytest fixtures shared across all test modules.

Provides mocked Azure SDK clients, sample data factories,
and patched environment variables for isolated testing.
"""

import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Ensure the functions directory is on the path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))


# ── Environment variables ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set standard environment variables for all tests."""
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "00000000-0000-0000-0000-000000000001")
    monkeypatch.setenv("AZURE_TENANT_ID", "00000000-0000-0000-0000-000000000002")
    monkeypatch.setenv("STORAGE_CONNECTION_STRING", "UseDevelopmentStorage=true")
    monkeypatch.setenv("LOGIC_APP_SLACK_WEBHOOK_URL", "https://example.com/slack")
    monkeypatch.setenv("LOGIC_APP_TEAMS_WEBHOOK_URL", "https://example.com/teams")
    monkeypatch.setenv("DAILY_BUDGET_LIMIT", "500")
    monkeypatch.setenv("MONTHLY_BUDGET_LIMIT", "15000")
    monkeypatch.setenv("COST_ANOMALY_THRESHOLD_PERCENT", "20")
    monkeypatch.setenv("WASTE_ALERT_MIN_SAVINGS", "50")


# ── Sample data factories ────────────────────────────────────────────────────

@pytest.fixture
def sample_cost_records():
    """Return a list of sample CostRecord dicts."""
    from shared.models import CostRecord
    return [
        CostRecord(
            date="2026-03-01",
            subscription_id="00000000-0000-0000-0000-000000000001",
            resource_group="rg-app-prod",
            service_name="Virtual Machines",
            cost=120.50,
            environment="prod",
            team="backend",
        ),
        CostRecord(
            date="2026-03-01",
            subscription_id="00000000-0000-0000-0000-000000000001",
            resource_group="rg-app-dev",
            service_name="Storage",
            cost=15.30,
            environment="dev",
            team="data",
        ),
        CostRecord(
            date="2026-03-02",
            subscription_id="00000000-0000-0000-0000-000000000001",
            resource_group="rg-app-prod",
            service_name="Virtual Machines",
            cost=250.00,
            environment="prod",
            team="backend",
        ),
        CostRecord(
            date="2026-03-02",
            subscription_id="00000000-0000-0000-0000-000000000001",
            resource_group="rg-app-dev",
            service_name="Storage",
            cost=14.80,
            environment="dev",
            team="data",
        ),
    ]


@pytest.fixture
def sample_waste_resources():
    """Return a list of sample WasteResource objects."""
    from shared.models import WasteResource
    return [
        WasteResource(
            resource_id="/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Compute/disks/disk-orphan-01",
            resource_type="Microsoft.Compute/disks",
            resource_name="disk-orphan-01",
            resource_group="rg-dev",
            subscription_id="00000000-0000-0000-0000-000000000001",
            waste_type="unattached_disk",
            estimated_monthly_savings=12.50,
            details="Unattached disk, size=250 GB",
        ),
        WasteResource(
            resource_id="/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Network/publicIPAddresses/pip-unused",
            resource_type="Microsoft.Network/publicIPAddresses",
            resource_name="pip-unused",
            resource_group="rg-dev",
            subscription_id="00000000-0000-0000-0000-000000000001",
            waste_type="unused_public_ip",
            estimated_monthly_savings=3.65,
            details="Public IP not associated with any resource",
        ),
        WasteResource(
            resource_id="/subscriptions/sub1/resourceGroups/rg-prod/providers/Microsoft.Network/loadBalancers/lb-idle",
            resource_type="Microsoft.Network/loadBalancers",
            resource_name="lb-idle",
            resource_group="rg-prod",
            subscription_id="00000000-0000-0000-0000-000000000001",
            waste_type="idle_load_balancer",
            estimated_monthly_savings=18.25,
            details="Load balancer has no backend pool members",
        ),
    ]


@pytest.fixture
def sample_recommendations():
    """Return a list of sample AdvisorRecommendation objects."""
    from shared.models import AdvisorRecommendation
    return [
        AdvisorRecommendation(
            recommendation_id="rec-001",
            category="Cost",
            impact="High",
            impacted_resource="vm-oversized-01",
            impacted_resource_type="Microsoft.Compute/virtualMachines",
            description="Right-size virtual machine vm-oversized-01",
            estimated_annual_savings=2400.00,
            action="Resize to Standard_B2s",
            subscription_id="00000000-0000-0000-0000-000000000001",
        ),
        AdvisorRecommendation(
            recommendation_id="rec-002",
            category="Cost",
            impact="Medium",
            impacted_resource="disk-premium-01",
            impacted_resource_type="Microsoft.Compute/disks",
            description="Switch disk-premium-01 from Premium to Standard SSD",
            estimated_annual_savings=360.00,
            action="Change disk tier",
            subscription_id="00000000-0000-0000-0000-000000000001",
        ),
    ]


# ── Mock Azure SDK clients ──────────────────────────────────────────────────

@pytest.fixture
def mock_credential():
    """Return a mocked DefaultAzureCredential."""
    return MagicMock()


@pytest.fixture
def mock_storage_client():
    """Return a mocked StorageClient that stores entities in memory."""
    from shared.storage_client import StorageClient

    mock = MagicMock(spec=StorageClient)
    _store: dict[str, list[dict]] = {}

    def upsert_entities(table_name, entities):
        _store.setdefault(table_name, []).extend(entities)
        return len(entities)

    def insert_entity(table_name, entity):
        _store.setdefault(table_name, []).append(entity)
        return True

    def get_all(table_name):
        return _store.get(table_name, [])

    def query_entities(table_name, filter_expr=None, top=None):
        return _store.get(table_name, [])

    mock.upsert_entities.side_effect = upsert_entities
    mock.insert_entity.side_effect = insert_entity
    mock.get_all.side_effect = get_all
    mock.query_entities.side_effect = query_entities
    mock._store = _store  # expose for assertions

    return mock
