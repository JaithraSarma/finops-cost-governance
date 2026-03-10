"""
FinOps Cost Governance - Azure Functions Entry Point

Registers all function blueprints:
  - cost_collector:          Daily cost data ingestion from Azure Cost Management API
  - resource_analyzer:       Identifies idle / underutilized resources (waste detection)
  - recommendation_fetcher:  Pulls Azure Advisor cost-optimization recommendations
  - alert_dispatcher:        Sends Slack / Teams alerts via Logic Apps webhooks
  - api_dashboard:           HTTP API consumed by Grafana dashboards
"""

import azure.functions as func

from blueprints.cost_collector import bp as cost_collector_bp
from blueprints.resource_analyzer import bp as resource_analyzer_bp
from blueprints.recommendation_fetcher import bp as recommendation_fetcher_bp
from blueprints.alert_dispatcher import bp as alert_dispatcher_bp
from blueprints.api_dashboard import bp as api_dashboard_bp

app = func.FunctionApp()

app.register_functions(cost_collector_bp)
app.register_functions(resource_analyzer_bp)
app.register_functions(recommendation_fetcher_bp)
app.register_functions(alert_dispatcher_bp)
app.register_functions(api_dashboard_bp)
