"""
Seed script — populates Azure Table Storage (or local Azurite) with
realistic sample data for local development and Grafana dashboard testing.

Usage:
    python scripts/seed_data.py
"""

import os
import sys
import random
from datetime import datetime, timedelta, timezone

# Ensure functions/ is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "functions"))

from shared.models import CostRecord, WasteResource, AdvisorRecommendation  # pylint: disable=import-error,wrong-import-position
from shared.storage_client import StorageClient  # pylint: disable=import-error,wrong-import-position
from shared.config import settings  # pylint: disable=import-error,wrong-import-position

# ── Configuration ────────────────────────────────────────────────────────────

TEAMS = ["backend", "frontend", "data", "platform", "ml-ops"]
ENVIRONMENTS = ["dev", "staging", "prod"]
SERVICES = [
    "Virtual Machines", "Storage", "SQL Database", "App Service",
    "Cosmos DB", "Functions", "Container Instances", "Key Vault",
    "Load Balancer", "Redis Cache",
]
RESOURCE_GROUPS = [
    "rg-app-prod", "rg-app-dev", "rg-data-prod", "rg-ml-staging",
    "rg-platform-shared", "rg-frontend-prod", "rg-frontend-dev",
]
SUBSCRIPTION_ID = settings.SUBSCRIPTION_ID or "00000000-0000-0000-0000-000000000001"


def seed_cost_records(storage: StorageClient, days: int = 30) -> int:
    """Generate daily cost records over the lookback window."""
    records = []
    end_date = datetime.now(timezone.utc)

    for day_offset in range(days):
        date = (end_date - timedelta(days=day_offset)).strftime("%Y-%m-%d")
        for rg in random.sample(RESOURCE_GROUPS, k=random.randint(3, len(RESOURCE_GROUPS))):
            for svc in random.sample(SERVICES, k=random.randint(2, 5)):
                cost = round(random.uniform(5, 350), 2)
                env = random.choice(ENVIRONMENTS)
                team = random.choice(TEAMS)
                records.append(CostRecord(
                    date=date,
                    subscription_id=SUBSCRIPTION_ID,
                    resource_group=rg,
                    service_name=svc,
                    cost=cost,
                    environment=env,
                    team=team,
                ))

    entities = [r.to_entity() for r in records]
    count = storage.upsert_entities(settings.COST_TABLE_NAME, entities)
    print(f"  Seeded {count} cost records")
    return count


def seed_waste_resources(storage: StorageClient) -> int:
    """Generate sample waste findings."""
    wastes = [
        WasteResource(
            resource_id=f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg-app-dev/providers/Microsoft.Compute/disks/disk-orphan-{i}",
            resource_type="Microsoft.Compute/disks",
            resource_name=f"disk-orphan-{i}",
            resource_group="rg-app-dev",
            subscription_id=SUBSCRIPTION_ID,
            waste_type="unattached_disk",
            estimated_monthly_savings=round(random.uniform(5, 50), 2),
            details=f"Unattached disk, size={random.choice([32, 64, 128, 256, 512])} GB",
        )
        for i in range(1, 6)
    ]
    wastes.extend([
        WasteResource(
            resource_id=f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg-platform-shared/providers/Microsoft.Network/publicIPAddresses/pip-unused-{i}",
            resource_type="Microsoft.Network/publicIPAddresses",
            resource_name=f"pip-unused-{i}",
            resource_group="rg-platform-shared",
            subscription_id=SUBSCRIPTION_ID,
            waste_type="unused_public_ip",
            estimated_monthly_savings=3.65,
            details="Public IP not associated with any resource",
        )
        for i in range(1, 4)
    ])
    wastes.append(WasteResource(
        resource_id=f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg-data-prod/providers/Microsoft.Network/loadBalancers/lb-idle-01",
        resource_type="Microsoft.Network/loadBalancers",
        resource_name="lb-idle-01",
        resource_group="rg-data-prod",
        subscription_id=SUBSCRIPTION_ID,
        waste_type="idle_load_balancer",
        estimated_monthly_savings=18.25,
        details="Load balancer has no backend pool members",
    ))
    wastes.append(WasteResource(
        resource_id=f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/rg-ml-staging/providers/Microsoft.Compute/virtualMachines/vm-oversized-01",
        resource_type="Microsoft.Compute/virtualMachines",
        resource_name="vm-oversized-01",
        resource_group="rg-ml-staging",
        subscription_id=SUBSCRIPTION_ID,
        waste_type="oversized_vm",
        estimated_monthly_savings=150.00,
        details="Avg CPU 2.3% over 7 days (threshold: 5%)",
    ))

    entities = [w.to_entity() for w in wastes]
    count = storage.upsert_entities(settings.WASTE_TABLE_NAME, entities)
    print(f"  Seeded {count} waste findings")
    return count


def seed_recommendations(storage: StorageClient) -> int:
    """Generate sample Advisor recommendations."""
    recs = [
        AdvisorRecommendation(
            recommendation_id="rec-001",
            category="Cost",
            impact="High",
            impacted_resource="vm-oversized-01",
            impacted_resource_type="Microsoft.Compute/virtualMachines",
            description="Right-size virtual machine vm-oversized-01 from Standard_D4s_v3 to Standard_B2s",
            estimated_annual_savings=2400.00,
            action="Resize VM",
            subscription_id=SUBSCRIPTION_ID,
        ),
        AdvisorRecommendation(
            recommendation_id="rec-002",
            category="Cost",
            impact="High",
            impacted_resource="sql-db-prod",
            impacted_resource_type="Microsoft.Sql/servers/databases",
            description="Use reserved capacity for SQL Database sql-db-prod",
            estimated_annual_savings=1800.00,
            action="Purchase reserved instance",
            subscription_id=SUBSCRIPTION_ID,
        ),
        AdvisorRecommendation(
            recommendation_id="rec-003",
            category="Cost",
            impact="Medium",
            impacted_resource="disk-premium-01",
            impacted_resource_type="Microsoft.Compute/disks",
            description="Switch disk-premium-01 from Premium SSD to Standard SSD",
            estimated_annual_savings=360.00,
            action="Change disk tier",
            subscription_id=SUBSCRIPTION_ID,
        ),
        AdvisorRecommendation(
            recommendation_id="rec-004",
            category="Cost",
            impact="Medium",
            impacted_resource="cosmos-db-prod",
            impacted_resource_type="Microsoft.DocumentDB/databaseAccounts",
            description="Reduce provisioned throughput on cosmos-db-prod during off-peak hours",
            estimated_annual_savings=720.00,
            action="Enable autoscale",
            subscription_id=SUBSCRIPTION_ID,
        ),
    ]

    entities = [r.to_entity() for r in recs]
    count = storage.upsert_entities(settings.RECOMMENDATIONS_TABLE_NAME, entities)
    print(f"  Seeded {count} recommendations")
    return count


def main():
    print("Seeding FinOps sample data...")
    print(f"  Connection: {settings.STORAGE_CONNECTION_STRING[:40]}...")

    storage = StorageClient()

    seed_cost_records(storage)
    seed_waste_resources(storage)
    seed_recommendations(storage)

    print("Done! Sample data is ready for Grafana dashboards.")


if __name__ == "__main__":
    main()
