"""
Azure Advisor client.

Fetches cost-optimisation recommendations from Azure Advisor and maps
them into AdvisorRecommendation data objects.
"""

from __future__ import annotations

import logging

from azure.core.exceptions import AzureError, HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.mgmt.advisor import AdvisorManagementClient

from shared.config import settings
from shared.models import AdvisorRecommendation

logger = logging.getLogger(__name__)


class AdvisorClient:
    """Wraps Azure Advisor SDK to retrieve cost recommendations."""

    def __init__(self, credential: DefaultAzureCredential | None = None):
        cred = credential or DefaultAzureCredential()
        self._client = AdvisorManagementClient(cred, settings.SUBSCRIPTION_ID)
        self._subscription_id = settings.SUBSCRIPTION_ID

    def get_cost_recommendations(self) -> list[AdvisorRecommendation]:
        """Return all Advisor recommendations in the 'Cost' category."""
        recommendations: list[AdvisorRecommendation] = []
        try:
            for rec in self._client.recommendations.list(filter="Category eq 'Cost'"):
                short_desc = rec.short_description
                description = ""
                if short_desc:
                    description = short_desc.solution or short_desc.problem or ""

                savings = self._extract_savings(rec)

                recommendations.append(AdvisorRecommendation(
                    recommendation_id=rec.name or "",
                    category="Cost",
                    impact=str(rec.impact or "Medium"),
                    impacted_resource=str(rec.impacted_value or ""),
                    impacted_resource_type=str(rec.impacted_field or ""),
                    description=description,
                    estimated_annual_savings=savings,
                    action=str(rec.recommendation_type_id or ""),
                    subscription_id=self._subscription_id,
                ))
        except (AzureError, HttpResponseError) as exc:
            logger.exception("Error fetching Advisor recommendations: %s", exc)

        logger.info("Fetched %d cost recommendations", len(recommendations))
        return recommendations

    @staticmethod
    def _extract_savings(rec) -> float:
        """
        Try to extract estimated annual savings from the recommendation
        extended properties.
        """
        try:
            ext = rec.extended_properties or {}
            for key in ("annualSavingsAmount", "savingsAmount", "annualSavings"):
                if key in ext:
                    return round(float(ext[key]), 2)
        except (ValueError, TypeError):
            pass
        return 0.0
