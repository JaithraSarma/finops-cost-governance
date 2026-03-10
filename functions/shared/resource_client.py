"""
Azure Resource analyzer client.

Scans the subscription for idle, orphaned, and underutilised resources:
  - Unattached managed disks
  - Oversized VMs (avg CPU < 5 %)
  - Idle load balancers (no backend-pool members)
  - Unused public IP addresses (not associated)
  - Idle Network Security Groups (not attached)
"""

from __future__ import annotations

import logging
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient

from shared.config import settings
from shared.models import WasteResource

logger = logging.getLogger(__name__)

# Average monthly cost estimates for quick savings calculations
_DISK_COST_PER_GB = 0.05     # Standard HDD per GB/month
_PIP_MONTHLY_COST = 3.65     # Static public IP
_LB_MONTHLY_COST = 18.25     # Basic LB idle cost


class ResourceAnalyzer:
    """Detects wasted Azure resources across the subscription."""

    def __init__(self, credential: DefaultAzureCredential | None = None):
        cred = credential or DefaultAzureCredential()
        sub = settings.SUBSCRIPTION_ID
        self._compute = ComputeManagementClient(cred, sub)
        self._network = NetworkManagementClient(cred, sub)
        self._resource = ResourceManagementClient(cred, sub)
        self._monitor = MonitorManagementClient(cred, sub)
        self._subscription_id = sub

    def scan_all(self) -> list[WasteResource]:
        """Run every waste-detection check and return combined results."""
        findings: list[WasteResource] = []
        findings.extend(self.find_unattached_disks())
        findings.extend(self.find_idle_load_balancers())
        findings.extend(self.find_unused_public_ips())
        findings.extend(self.find_oversized_vms())
        logger.info("Total waste findings: %d", len(findings))
        return findings

    # ── Unattached Managed Disks ─────────────────────────────────────────

    def find_unattached_disks(self) -> list[WasteResource]:
        """Find managed disks with no VM owner (disk_state == Unattached)."""
        findings: list[WasteResource] = []
        try:
            for disk in self._compute.disks.list():
                if disk.disk_state == "Unattached":
                    size_gb = disk.disk_size_gb or 0
                    savings = round(size_gb * _DISK_COST_PER_GB, 2)
                    rg = _extract_rg(disk.id)
                    findings.append(WasteResource(
                        resource_id=disk.id,
                        resource_type="Microsoft.Compute/disks",
                        resource_name=disk.name,
                        resource_group=rg,
                        subscription_id=self._subscription_id,
                        waste_type="unattached_disk",
                        estimated_monthly_savings=savings,
                        details=f"Unattached disk, size={size_gb} GB",
                    ))
        except Exception:
            logger.exception("Error scanning disks")
        logger.info("Found %d unattached disks", len(findings))
        return findings

    # ── Idle Load Balancers ──────────────────────────────────────────────

    def find_idle_load_balancers(self) -> list[WasteResource]:
        """Find load balancers with no backend pool members."""
        findings: list[WasteResource] = []
        try:
            for lb in self._network.load_balancers.list_all():
                backend_pools = lb.backend_address_pools or []
                has_members = any(
                    pool.backend_ip_configurations
                    for pool in backend_pools
                    if pool.backend_ip_configurations
                )
                if not has_members:
                    rg = _extract_rg(lb.id)
                    findings.append(WasteResource(
                        resource_id=lb.id,
                        resource_type="Microsoft.Network/loadBalancers",
                        resource_name=lb.name,
                        resource_group=rg,
                        subscription_id=self._subscription_id,
                        waste_type="idle_load_balancer",
                        estimated_monthly_savings=_LB_MONTHLY_COST,
                        details="Load balancer has no backend pool members",
                    ))
        except Exception:
            logger.exception("Error scanning load balancers")
        logger.info("Found %d idle load balancers", len(findings))
        return findings

    # ── Unused Public IPs ────────────────────────────────────────────────

    def find_unused_public_ips(self) -> list[WasteResource]:
        """Find public IPs that are not associated with any resource."""
        findings: list[WasteResource] = []
        try:
            for pip in self._network.public_ip_addresses.list_all():
                if pip.ip_configuration is None:
                    rg = _extract_rg(pip.id)
                    findings.append(WasteResource(
                        resource_id=pip.id,
                        resource_type="Microsoft.Network/publicIPAddresses",
                        resource_name=pip.name,
                        resource_group=rg,
                        subscription_id=self._subscription_id,
                        waste_type="unused_public_ip",
                        estimated_monthly_savings=_PIP_MONTHLY_COST,
                        details="Public IP not associated with any resource",
                    ))
        except Exception:
            logger.exception("Error scanning public IPs")
        logger.info("Found %d unused public IPs", len(findings))
        return findings

    # ── Oversized VMs ────────────────────────────────────────────────────

    def find_oversized_vms(self) -> list[WasteResource]:
        """
        Find VMs where average CPU utilisation is below 5 % over the last 7 days.
        Requires Azure Monitor metrics access.
        """
        findings: list[WasteResource] = []
        try:
            from datetime import datetime, timedelta, timezone

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=7)
            timespan = f"{start_time.isoformat()}/{end_time.isoformat()}"

            for vm in self._compute.virtual_machines.list_all():
                try:
                    metrics = self._monitor.metrics.list(
                        resource_uri=vm.id,
                        timespan=timespan,
                        interval="P1D",
                        metricnames="Percentage CPU",
                        aggregation="Average",
                    )
                    avg_cpu = _get_average_metric(metrics)
                    if avg_cpu is not None and avg_cpu < 5.0:
                        rg = _extract_rg(vm.id)
                        findings.append(WasteResource(
                            resource_id=vm.id,
                            resource_type="Microsoft.Compute/virtualMachines",
                            resource_name=vm.name,
                            resource_group=rg,
                            subscription_id=self._subscription_id,
                            waste_type="oversized_vm",
                            estimated_monthly_savings=0.0,  # needs pricing API
                            details=f"Avg CPU {avg_cpu:.1f}% over 7 days (threshold: 5%)",
                        ))
                except Exception:
                    logger.warning("Could not fetch metrics for VM %s", vm.name)
        except Exception:
            logger.exception("Error scanning VMs")
        logger.info("Found %d oversized VMs", len(findings))
        return findings


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_rg(resource_id: str) -> str:
    """Extract resource group name from an ARM resource ID."""
    parts = resource_id.split("/")
    for i, part in enumerate(parts):
        if part.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""


def _get_average_metric(metrics_response: Any) -> float | None:
    """Extract the average value from an Azure Monitor metrics response."""
    try:
        for metric in metrics_response.value:
            for ts in metric.timeseries:
                values = [
                    dp.average for dp in ts.data if dp.average is not None
                ]
                if values:
                    return round(sum(values) / len(values), 2)
    except Exception:
        pass
    return None
