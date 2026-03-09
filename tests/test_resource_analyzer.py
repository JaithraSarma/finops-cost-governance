"""Tests for the resource_analyzer (waste detection) logic."""

from unittest.mock import MagicMock, patch

from shared.resource_client import ResourceAnalyzer, _extract_rg, _get_average_metric  # pylint: disable=import-error


class TestExtractRg:
    """Test the helper that extracts resource group from ARM IDs."""

    def test_standard_id(self):
        rid = "/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Compute/disks/disk1"
        assert _extract_rg(rid) == "rg-dev"

    def test_case_insensitive(self):
        rid = "/subscriptions/sub1/resourcegroups/rg-prod/providers/Microsoft.Network/publicIPAddresses/pip1"
        assert _extract_rg(rid) == "rg-prod"

    def test_no_rg(self):
        assert _extract_rg("/subscriptions/sub1") == ""


class TestGetAverageMetric:
    def test_valid_metrics(self):
        dp1 = MagicMock(average=4.0)
        dp2 = MagicMock(average=6.0)
        dp3 = MagicMock(average=5.0)
        ts = MagicMock(data=[dp1, dp2, dp3])
        metric = MagicMock(timeseries=[ts])
        response = MagicMock(value=[metric])
        assert _get_average_metric(response) == 5.0

    def test_empty_metrics(self):
        response = MagicMock(value=[])
        assert _get_average_metric(response) is None

    def test_none_averages(self):
        dp1 = MagicMock(average=None)
        ts = MagicMock(data=[dp1])
        metric = MagicMock(timeseries=[ts])
        response = MagicMock(value=[metric])
        assert _get_average_metric(response) is None


class TestResourceAnalyzer:
    """Test waste detection for various resource types."""

    # pylint: disable=unused-argument  # @patch args required positionally

    @patch("shared.resource_client.MonitorManagementClient")
    @patch("shared.resource_client.NetworkManagementClient")
    @patch("shared.resource_client.ResourceManagementClient")
    @patch("shared.resource_client.ComputeManagementClient")
    @patch("shared.resource_client.DefaultAzureCredential")
    def test_find_unattached_disks(self, mock_cred, mock_compute, mock_resource,
                                    mock_network, mock_monitor):
        """Should detect disks with disk_state == Unattached."""
        disk = MagicMock()
        disk.disk_state = "Unattached"
        disk.disk_size_gb = 128
        disk.name = "orphan-disk-01"
        disk.id = "/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Compute/disks/orphan-disk-01"

        attached_disk = MagicMock()
        attached_disk.disk_state = "Attached"
        attached_disk.name = "active-disk"
        attached_disk.id = "/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Compute/disks/active-disk"

        mock_compute.return_value.disks.list.return_value = [disk, attached_disk]

        analyzer = ResourceAnalyzer(credential=mock_cred())
        findings = analyzer.find_unattached_disks()

        assert len(findings) == 1
        assert findings[0].waste_type == "unattached_disk"
        assert findings[0].resource_name == "orphan-disk-01"
        assert findings[0].estimated_monthly_savings == 6.40  # 128 * 0.05

    @patch("shared.resource_client.MonitorManagementClient")
    @patch("shared.resource_client.NetworkManagementClient")
    @patch("shared.resource_client.ResourceManagementClient")
    @patch("shared.resource_client.ComputeManagementClient")
    @patch("shared.resource_client.DefaultAzureCredential")
    def test_find_idle_load_balancers(self, mock_cred, mock_compute, mock_resource,
                                       mock_network, mock_monitor):
        """Should detect LBs with no backend pool members."""
        idle_lb = MagicMock()
        idle_lb.name = "lb-idle"
        idle_lb.id = "/subscriptions/sub1/resourceGroups/rg-prod/providers/Microsoft.Network/loadBalancers/lb-idle"
        pool = MagicMock()
        pool.backend_ip_configurations = None
        idle_lb.backend_address_pools = [pool]

        mock_network.return_value.load_balancers.list_all.return_value = [idle_lb]

        analyzer = ResourceAnalyzer(credential=mock_cred())
        findings = analyzer.find_idle_load_balancers()

        assert len(findings) == 1
        assert findings[0].waste_type == "idle_load_balancer"

    @patch("shared.resource_client.MonitorManagementClient")
    @patch("shared.resource_client.NetworkManagementClient")
    @patch("shared.resource_client.ResourceManagementClient")
    @patch("shared.resource_client.ComputeManagementClient")
    @patch("shared.resource_client.DefaultAzureCredential")
    def test_find_unused_public_ips(self, mock_cred, mock_compute, mock_resource,
                                     mock_network, mock_monitor):
        """Should detect public IPs without an ip_configuration."""
        unused_pip = MagicMock()
        unused_pip.name = "pip-orphan"
        unused_pip.id = "/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Network/publicIPAddresses/pip-orphan"
        unused_pip.ip_configuration = None

        used_pip = MagicMock()
        used_pip.name = "pip-active"
        used_pip.ip_configuration = MagicMock()

        mock_network.return_value.public_ip_addresses.list_all.return_value = [unused_pip, used_pip]

        analyzer = ResourceAnalyzer(credential=mock_cred())
        findings = analyzer.find_unused_public_ips()

        assert len(findings) == 1
        assert findings[0].waste_type == "unused_public_ip"
        assert findings[0].resource_name == "pip-orphan"

    @patch("shared.resource_client.MonitorManagementClient")
    @patch("shared.resource_client.NetworkManagementClient")
    @patch("shared.resource_client.ResourceManagementClient")
    @patch("shared.resource_client.ComputeManagementClient")
    @patch("shared.resource_client.DefaultAzureCredential")
    def test_scan_all_combines_results(self, mock_cred, mock_compute, mock_resource,
                                        mock_network, mock_monitor):
        """scan_all should combine findings from all checks."""
        # Setup: 1 unattached disk, 0 LBs, 0 PIPs, 0 VMs
        disk = MagicMock()
        disk.disk_state = "Unattached"
        disk.disk_size_gb = 64
        disk.name = "disk-1"
        disk.id = "/subscriptions/sub1/resourceGroups/rg-dev/providers/Microsoft.Compute/disks/disk-1"
        mock_compute.return_value.disks.list.return_value = [disk]
        mock_network.return_value.load_balancers.list_all.return_value = []
        mock_network.return_value.public_ip_addresses.list_all.return_value = []
        mock_compute.return_value.virtual_machines.list_all.return_value = []

        analyzer = ResourceAnalyzer(credential=mock_cred())
        findings = analyzer.scan_all()

        assert len(findings) == 1
        assert findings[0].waste_type == "unattached_disk"
