"""
api_dashboard blueprint — HTTP-triggered Azure Functions

Exposes a REST API consumed by Grafana (or any HTTP data source) to
visualise cost trends, waste reports, and recommendations.

Endpoints:
  GET /api/health                → Health check
  GET /api/costs/summary         → Current month cost summary
  GET /api/costs/trends          → Daily cost trends
  GET /api/costs/by-team         → Costs grouped by team tag
  GET /api/costs/by-environment  → Costs grouped by environment tag
  GET /api/waste/report          → Active waste findings
  GET /api/recommendations       → Active Advisor recommendations
  GET /api/alerts/recent         → Recent alerts
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

import azure.functions as func

from shared.config import settings
from shared.storage_client import StorageClient

logger = logging.getLogger(__name__)
bp = func.Blueprint()


def _json_response(body: dict | list, status: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(body, default=str),
        status_code=status,
        mimetype="application/json",
    )


# ── Health ───────────────────────────────────────────────────────────────────

@bp.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
    })


# ── Cost Summary ─────────────────────────────────────────────────────────────

@bp.route(route="costs/summary", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def costs_summary(req: func.HttpRequest) -> func.HttpResponse:
    """Return aggregated cost summary for the current month."""
    storage = StorageClient()
    records = storage.get_all(settings.COST_TABLE_NAME)

    total_cost = sum(float(r.get("cost", 0)) for r in records)
    unique_rgs = {r.get("resource_group", "") for r in records}
    unique_services = {r.get("service_name", "") for r in records}

    return _json_response({
        "total_cost": round(total_cost, 2),
        "currency": "USD",
        "resource_groups": len(unique_rgs),
        "services": len(unique_services),
        "record_count": len(records),
        "budget_limit": settings.MONTHLY_BUDGET_LIMIT,
        "budget_utilisation_pct": round((total_cost / settings.MONTHLY_BUDGET_LIMIT) * 100, 1)
        if settings.MONTHLY_BUDGET_LIMIT > 0 else 0,
    })


# ── Cost Trends ──────────────────────────────────────────────────────────────

@bp.route(route="costs/trends", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def costs_trends(req: func.HttpRequest) -> func.HttpResponse:
    """Return daily cost totals for trend charting."""
    storage = StorageClient()
    records = storage.get_all(settings.COST_TABLE_NAME)

    daily: dict[str, float] = defaultdict(float)
    for r in records:
        date = r.get("date", "unknown")
        daily[date] += float(r.get("cost", 0))

    trends = [
        {"date": d, "cost": round(c, 2)}
        for d, c in sorted(daily.items())
    ]
    return _json_response(trends)


# ── Cost by Team ─────────────────────────────────────────────────────────────

@bp.route(route="costs/by-team", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def costs_by_team(req: func.HttpRequest) -> func.HttpResponse:
    """Return costs grouped by the 'team' tag."""
    storage = StorageClient()
    records = storage.get_all(settings.COST_TABLE_NAME)

    by_team: dict[str, float] = defaultdict(float)
    for r in records:
        team = r.get("team", "") or "untagged"
        by_team[team] += float(r.get("cost", 0))

    result = [
        {"team": t, "cost": round(c, 2)}
        for t, c in sorted(by_team.items(), key=lambda x: -x[1])
    ]
    return _json_response(result)


# ── Cost by Environment ──────────────────────────────────────────────────────

@bp.route(route="costs/by-environment", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def costs_by_environment(req: func.HttpRequest) -> func.HttpResponse:
    """Return costs grouped by the 'environment' tag."""
    storage = StorageClient()
    records = storage.get_all(settings.COST_TABLE_NAME)

    by_env: dict[str, float] = defaultdict(float)
    for r in records:
        env = r.get("environment", "") or "untagged"
        by_env[env] += float(r.get("cost", 0))

    result = [
        {"environment": e, "cost": round(c, 2)}
        for e, c in sorted(by_env.items(), key=lambda x: -x[1])
    ]
    return _json_response(result)


# ── Waste Report ─────────────────────────────────────────────────────────────

@bp.route(route="waste/report", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def waste_report(req: func.HttpRequest) -> func.HttpResponse:
    """Return all identified waste resources."""
    storage = StorageClient()
    findings = storage.get_all(settings.WASTE_TABLE_NAME)

    total_savings = sum(float(f.get("estimated_monthly_savings", 0)) for f in findings)

    return _json_response({
        "total_findings": len(findings),
        "total_estimated_monthly_savings": round(total_savings, 2),
        "findings": findings,
    })


# ── Recommendations ──────────────────────────────────────────────────────────

@bp.route(route="recommendations", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def recommendations(req: func.HttpRequest) -> func.HttpResponse:
    """Return Azure Advisor cost recommendations."""
    storage = StorageClient()
    recs = storage.get_all(settings.RECOMMENDATIONS_TABLE_NAME)

    total_annual = sum(float(r.get("estimated_annual_savings", 0)) for r in recs)

    return _json_response({
        "total_recommendations": len(recs),
        "total_estimated_annual_savings": round(total_annual, 2),
        "recommendations": recs,
    })


# ── Recent Alerts ────────────────────────────────────────────────────────────

@bp.route(route="alerts/recent", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def alerts_recent(req: func.HttpRequest) -> func.HttpResponse:
    """Return the 50 most recent alerts."""
    storage = StorageClient()
    alerts = storage.get_all(settings.ALERTS_TABLE_NAME)

    # Sort by created_at descending and take top 50
    alerts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
    return _json_response(alerts[:50])
