"""Tests for the recommendation_fetcher (Azure Advisor) logic."""

from unittest.mock import MagicMock, patch

from shared.advisor_client import AdvisorClient


class TestAdvisorClient:
    """Test Azure Advisor cost recommendation fetching."""

    @patch("shared.advisor_client.AdvisorManagementClient")
    @patch("shared.advisor_client.DefaultAzureCredential")
    def test_get_cost_recommendations(self, mock_cred, mock_advisor):
        """Should parse Advisor response into AdvisorRecommendation objects."""
        rec1 = MagicMock()
        rec1.name = "rec-001"
        rec1.impact = "High"
        rec1.impacted_value = "vm-oversized-01"
        rec1.impacted_field = "Microsoft.Compute/virtualMachines"
        rec1.recommendation_type_id = "resize-vm"
        rec1.short_description = MagicMock()
        rec1.short_description.solution = "Right-size virtual machine"
        rec1.short_description.problem = "VM is oversized"
        rec1.extended_properties = {"annualSavingsAmount": "2400.00"}

        rec2 = MagicMock()
        rec2.name = "rec-002"
        rec2.impact = "Medium"
        rec2.impacted_value = "disk-premium-01"
        rec2.impacted_field = "Microsoft.Compute/disks"
        rec2.recommendation_type_id = "change-disk-tier"
        rec2.short_description = MagicMock()
        rec2.short_description.solution = "Switch to Standard SSD"
        rec2.short_description.problem = None
        rec2.extended_properties = {"annualSavingsAmount": "360.00"}

        mock_advisor.return_value.recommendations.list.return_value = [rec1, rec2]

        client = AdvisorClient(credential=mock_cred())
        recommendations = client.get_cost_recommendations()

        assert len(recommendations) == 2
        assert recommendations[0].impact == "High"
        assert recommendations[0].estimated_annual_savings == 2400.00
        assert recommendations[1].description == "Switch to Standard SSD"

    @patch("shared.advisor_client.AdvisorManagementClient")
    @patch("shared.advisor_client.DefaultAzureCredential")
    def test_empty_recommendations(self, mock_cred, mock_advisor):
        """No recommendations should return an empty list."""
        mock_advisor.return_value.recommendations.list.return_value = []

        client = AdvisorClient(credential=mock_cred())
        recs = client.get_cost_recommendations()
        assert recs == []

    @patch("shared.advisor_client.AdvisorManagementClient")
    @patch("shared.advisor_client.DefaultAzureCredential")
    def test_savings_extraction_fallback(self, mock_cred, mock_advisor):
        """Should return 0.0 when no savings amount is in extended properties."""
        rec = MagicMock()
        rec.name = "rec-003"
        rec.impact = "Low"
        rec.impacted_value = "resource-x"
        rec.impacted_field = "Microsoft.Storage/storageAccounts"
        rec.recommendation_type_id = "optimize-storage"
        rec.short_description = MagicMock()
        rec.short_description.solution = "Use lifecycle management"
        rec.short_description.problem = None
        rec.extended_properties = {}

        mock_advisor.return_value.recommendations.list.return_value = [rec]

        client = AdvisorClient(credential=mock_cred())
        recs = client.get_cost_recommendations()

        assert len(recs) == 1
        assert recs[0].estimated_annual_savings == 0.0
