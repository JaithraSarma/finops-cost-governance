"""
Azure Cost Management API client.

Queries the Cost Management REST API to retrieve daily cost breakdowns
grouped by resource group, service (meter category), and tags.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryDefinition,
    QueryTimePeriod,
    QueryDataset,
    QueryAggregation,
    QueryGrouping,
    ExportType,
    TimeframeType,
)

from shared.config import settings
from shared.models import CostRecord

logger = logging.getLogger(__name__)


class CostClient:
    """Wraps Azure Cost Management SDK to fetch cost data."""

    def __init__(self, credential: DefaultAzureCredential | None = None):
        self._credential = credential or DefaultAzureCredential()
        self._client = CostManagementClient(self._credential)
        self._subscription_id = settings.SUBSCRIPTION_ID

    @property
    def scope(self) -> str:
        return f"/subscriptions/{self._subscription_id}"

    def query_daily_costs(self, lookback_days: int | None = None) -> list[CostRecord]:
        """
        Query daily costs for the subscription, grouped by ResourceGroup
        and MeterCategory, over the specified lookback window.
        """
        days = lookback_days or settings.COST_LOOKBACK_DAYS
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        query = QueryDefinition(
            type=ExportType.ACTUAL_COST,
            timeframe=TimeframeType.CUSTOM,
            time_period=QueryTimePeriod(
                from_property=start_date,
                to=end_date,
            ),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={
                    "totalCost": QueryAggregation(name="Cost", function="Sum"),
                },
                grouping=[
                    QueryGrouping(type="Dimension", name="ResourceGroup"),
                    QueryGrouping(type="Dimension", name="MeterCategory"),
                ],
            ),
        )

        logger.info("Querying costs for %s (last %d days)", self.scope, days)
        result = self._client.query.usage(scope=self.scope, parameters=query)
        return self._parse_cost_result(result)

    def _parse_cost_result(self, result: Any) -> list[CostRecord]:
        """Parse the query response into CostRecord objects."""
        records: list[CostRecord] = []
        if not result or not result.rows:
            logger.warning("No cost data returned from API")
            return records

        columns = [col.name for col in result.columns]
        cost_idx = columns.index("Cost") if "Cost" in columns else 0
        rg_idx = columns.index("ResourceGroup") if "ResourceGroup" in columns else 1
        meter_idx = columns.index("MeterCategory") if "MeterCategory" in columns else 2
        date_idx = columns.index("UsageDate") if "UsageDate" in columns else 3

        for row in result.rows:
            raw_date = str(int(row[date_idx]))
            formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

            record = CostRecord(
                date=formatted_date,
                subscription_id=self._subscription_id,
                resource_group=str(row[rg_idx]),
                service_name=str(row[meter_idx]),
                cost=round(float(row[cost_idx]), 2),
            )
            records.append(record)

        logger.info("Parsed %d cost records", len(records))
        return records

    def get_current_month_total(self) -> float:
        """Return total cost for the current billing month."""
        query = QueryDefinition(
            type=ExportType.ACTUAL_COST,
            timeframe=TimeframeType.MONTH_TO_DATE,
            dataset=QueryDataset(
                granularity="None",
                aggregation={
                    "totalCost": QueryAggregation(name="Cost", function="Sum"),
                },
            ),
        )
        result = self._client.query.usage(scope=self.scope, parameters=query)
        if result and result.rows:
            return round(float(result.rows[0][0]), 2)
        return 0.0
