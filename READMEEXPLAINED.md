# READMEEXPLAINED.md — Interview-Ready Deep Dive

> **Purpose**: This document explains every aspect of the FinOps Cost Governance
> project in depth — architecture decisions, code patterns, Azure services,
> Terraform design, testing strategy, and real-world trade-offs.  After reading
> this you should be able to confidently answer any technical interview question
> about the project.

---

## Table of Contents

1. [What Is FinOps?](#1-what-is-finops)
2. [Why This Project Exists](#2-why-this-project-exists)
3. [Architecture Walkthrough](#3-architecture-walkthrough)
4. [Azure Functions — Deep Dive](#4-azure-functions--deep-dive)
5. [Shared Modules Explained](#5-shared-modules-explained)
6. [Each Function Blueprint in Detail](#6-each-function-blueprint-in-detail)
7. [Azure Table Storage Design](#7-azure-table-storage-design)
8. [Alerting Pipeline — Queue Decoupling](#8-alerting-pipeline--queue-decoupling)
9. [Azure Policy Governance](#9-azure-policy-governance)
10. [Logic Apps Notification Workflows](#10-logic-apps-notification-workflows)
11. [Grafana Dashboards & Infinity Datasource](#11-grafana-dashboards--infinity-datasource)
12. [Terraform Infrastructure-as-Code](#12-terraform-infrastructure-as-code)
13. [Security & Identity](#13-security--identity)
14. [Testing Strategy](#14-testing-strategy)
15. [Local Development Environment](#15-local-development-environment)
16. [Deployment Flow](#16-deployment-flow)
17. [Design Decisions & Trade-offs](#17-design-decisions--trade-offs)
18. [Interview Questions & Answers](#18-interview-questions--answers)

---

## 1. What Is FinOps?

FinOps (Cloud Financial Operations) is a cultural practice and set of tools that
bring financial accountability to the variable spending of cloud computing.  The
FinOps Foundation defines three lifecycle phases:

| Phase | Goal | This Project's Coverage |
|---|---|---|
| **Inform** | Make cloud costs visible to all stakeholders | Cost collector, dashboard API, Grafana dashboards |
| **Optimize** | Identify and act on savings opportunities | Resource analyzer (waste detection), Advisor recommendations |
| **Operate** | Embed governance and automation into daily operations | Azure Policy (tag enforcement), alert dispatcher, Terraform IaC |

Key FinOps principles implemented here:
- **Teams need to collaborate** — Dashboards are shared; alerts go to Slack and Teams.
- **Everyone takes ownership** — Mandatory tagging gives every resource an owner.
- **Data should be timely** — Daily automated collection; queue-based real-time alerts.
- **Decisions are driven by business value** — Every waste finding and recommendation includes a dollar amount.

---

## 2. Why This Project Exists

Most organisations start their cloud journey without cost visibility.  By the
time they notice overspending, they have:

- Orphaned disks from deleted VMs still accruing charges.
- Oversized VMs running at 2-3% CPU 24/7.
- Resources missing tags, making chargeback impossible.
- No budget thresholds or anomaly detection.

This project provides an **automated, serverless, zero-idle-cost** solution that
runs every day, collects data, detects waste, fetches recommendations, fires
alerts, and serves dashboards — all for the cost of a few Azure Function
executions per day.

---

## 3. Architecture Walkthrough

### Data Flow (Chronological)

```
06:00 UTC ─ cost_collector (Timer)
  │  Calls Azure Cost Management API
  │  Stores daily cost rows in DailyCosts table
  │  Checks: Is monthly total > budget?  → enqueue CostAlert
  │  Checks: Is today's cost > yesterday * threshold? → enqueue CostAlert
  │
07:00 UTC ─ resource_analyzer (Timer)
  │  Calls Compute, Network, Monitor SDKs
  │  Finds: unattached disks, idle LBs, unused IPs, oversized VMs
  │  Stores findings in WasteFindings table
  │  Enqueues a summary CostAlert
  │
08:00 UTC ─ recommendation_fetcher (Timer)
  │  Calls Azure Advisor SDK
  │  Stores cost-category recommendations in AdvisorRecommendations table
  │  Enqueues CostAlert for each high-impact recommendation
  │
Continuous ─ alert_dispatcher (Queue trigger)
  │  Dequeues from "cost-alerts" queue
  │  Persists to Alerts table
  │  POSTs to Slack webhook (Logic App)
  │  POSTs to Teams webhook (Logic App)
  │
On-demand ─ api_dashboard (HTTP trigger)
     Reads tables, aggregates data, returns JSON
     Grafana polls these endpoints every 5 minutes
```

### Why Sequential Scheduling?

Azure Cost Management API and the Resource/Compute/Network SDKs all have rate
limits.  By spacing the three collection functions 1 hour apart:

1. We avoid hitting throttling limits.
2. Cost data from 06:00 is available for the 07:00 resource analysis context.
3. Each function can be monitored and debugged independently via App Insights.

---

## 4. Azure Functions — Deep Dive

### Programming Model: Python v2

This project uses the **v2 programming model** introduced in the Azure Functions
Python SDK.  Key differences from v1:

| Feature | v1 | v2 (this project) |
|---|---|---|
| Trigger definition | function.json files | Decorators in Python code |
| Project structure | One folder per function | Blueprints — any file structure |
| Entry point | Individual `__init__.py` files | Single `function_app.py` registering blueprints |

### Blueprint Pattern

Each concern (cost collection, resource analysis, etc.) lives in its own
blueprint file under `functions/blueprints/`.  The main `function_app.py` simply
imports and registers them:

```python
import azure.functions as func
from blueprints.cost_collector import bp as cost_bp
from blueprints.resource_analyzer import bp as resource_bp
# ...

app = func.FunctionApp()
app.register_blueprint(cost_bp)
app.register_blueprint(resource_bp)
# ...
```

**Why blueprints?**
- Separation of concerns: each file owns its trigger, logic, and tests.
- Parallel development: multiple engineers can work on different blueprints.
- Cleaner testing: mock only the dependencies of the specific blueprint.

### Hosting: Consumption Plan

- **Pay per execution**: No charges when functions aren't running.
- **Auto-scale**: Azure allocates instances as needed (though for daily timers,
  we typically only need one instance).
- **Cold start**: ~2-5 seconds for Python. Acceptable for timer-triggered
  functions; the HTTP dashboard endpoints may occasionally have cold starts.

### Key Configuration (`host.json`)

```json
{
  "functionTimeout": "00:10:00",
  "extensionBundle": {
    "id": "Microsoft.Azure.Functions.ExtensionBundle",
    "version": "[4.*, 5.0.0)"
  }
}
```

- **10-minute timeout**: Cost Management queries can be slow for large subscriptions.
- **Extension bundle v4**: Provides storage queue, table, and timer bindings out of the box.

---

## 5. Shared Modules Explained

All shared modules live in `functions/shared/` and are imported by the
blueprints.

### `config.py` — Centralised Settings

A single `Settings` dataclass reads all configuration from environment variables
with sensible defaults:

```python
@dataclass
class Settings:
    SUBSCRIPTION_ID: str = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    STORAGE_CONNECTION_STRING: str = os.environ.get(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;..."
    )
    MONTHLY_BUDGET_USD: float = float(os.environ.get("MONTHLY_BUDGET_USD", "10000"))
    # ...
```

**Interview point**: Using environment variables (not hard-coded values) follows
the [Twelve-Factor App](https://12factor.net/config) methodology.  In Azure, these
are set as Function App Application Settings and injected automatically.

### `models.py` — Data Classes

Four dataclasses with built-in serialisation:

| Model | Table | Partition Key | Row Key |
|---|---|---|---|
| `CostRecord` | DailyCosts | `{subscription_id}_{date}` | `{resource_group}_{service_name}` |
| `WasteResource` | WasteFindings | `{subscription_id}` | `{resource_id}` (sanitised) |
| `AdvisorRecommendation` | AdvisorRecommendations | `{subscription_id}` | `{recommendation_id}` |
| `CostAlert` | Alerts | `{alert_type}` | `{timestamp}` |

Each model has:
- `partition_key` / `row_key` properties — for Table Storage.
- `to_entity()` — converts to a dict suitable for `upsert_entity`.
- `to_dict()` — converts to a JSON-serialisable dict for the API layer.

**Interview point**: The partition key design ensures related data lives on the
same storage partition for efficient queries.  For example, querying all costs for
a single day uses a partition key filter, which is O(1) in Azure Table Storage.

### `cost_client.py` — Cost Management Wrapper

Wraps `CostManagementClient.usage.query()` with a `QueryDefinition` that groups
costs by `ResourceGroup` and `ServiceName` on a daily granularity.

Key method: `query_daily_costs(lookback_days)`.

**Interview point**: The Cost Management API returns a tabular result set.  The
column order is determined by the `grouping` and `aggregation` configuration in
the query.  The client maps column indices to `CostRecord` fields.

### `resource_client.py` — Waste Scanner

Four detection methods:

| Method | What It Finds | How |
|---|---|---|
| `find_unattached_disks()` | Disks with no VM owner | `disk.managed_by is None` |
| `find_idle_load_balancers()` | LBs with empty backend pools | `len(lb.backend_address_pools) == 0` |
| `find_unused_public_ips()` | Public IPs not attached to anything | `ip.ip_configuration is None` |
| `find_oversized_vms()` | VMs with avg CPU below threshold | Azure Monitor metric `Percentage CPU` over 7 days |

**Interview point**: `find_oversized_vms()` calls `_get_average_metric()` which
queries Azure Monitor for the `Percentage CPU` metric using a 7-day timegrain.
The helper computes the mean across all data points.  If avg < 5% (configurable),
the VM is flagged.

### `advisor_client.py` — Advisor Recommendations

Filters Advisor recommendations to `category == "Cost"` and extracts the
`annualSavingsAmount` from the recommendation's `extended_properties`.

### `alert_client.py` — Webhook Dispatcher

Sends formatted messages to two channels:

- **Slack**: Uses Slack's `mrkdwn` format with `blocks` and `attachments`.
  Severity is mapped to a color bar (red for `critical`, yellow for `warning`).
- **Teams**: Uses the Office 365 `MessageCard` schema with `themeColor` and
  `sections`.

Both methods are independent — if one fails, the other still fires.

### `storage_client.py` — Table Storage CRUD

A thin wrapper over `azure-data-tables`:

- Auto-creates tables on first use (`create_table_if_not_exists`).
- `upsert_entities(table, entities)` — bulk upsert (merge mode).
- `query_entities(table, filter)` — OData filter queries.
- Thread-safe: creates a new `TableClient` per operation.

**Interview point**: Using `UpdateMode.MERGE` means we only overwrite fields
that are present in the new entity.  If a previous run stored extra fields,
they are preserved.

---

## 6. Each Function Blueprint in Detail

### `cost_collector.py`

**Trigger**: Timer — `0 0 6 * * *` (daily at 06:00 UTC).

Logic flow:
1. Create a `CostClient` and query the last N days of costs.
2. Upsert all `CostRecord` entities into the DailyCosts table.
3. Sum today's total and compare against the monthly budget.
   - If exceeded → enqueue a `critical` `CostAlert`.
4. Compare today's cost against yesterday's cost.
   - If the increase exceeds the anomaly threshold % → enqueue a `warning` `CostAlert`.

**Interview point**: The anomaly detection is a simple day-over-day percentage
change.  In a production system you might use a rolling average or standard
deviation for a more robust anomaly model — but for a governance tool, a
percentage spike is actionable and easy to understand.

### `resource_analyzer.py`

**Trigger**: Timer — `0 0 7 * * *` (daily at 07:00 UTC).

Logic flow:
1. Create a `ResourceAnalyzer` and call `scan_all()`.
2. `scan_all()` runs all four detection methods in sequence.
3. Upsert findings into the WasteFindings table.
4. Build a summary alert with total savings and per-type breakdown.

### `recommendation_fetcher.py`

**Trigger**: Timer — `0 0 8 * * *` (daily at 08:00 UTC).

Logic flow:
1. Create an `AdvisorClient` and fetch cost recommendations.
2. Upsert into AdvisorRecommendations table.
3. For each recommendation with `impact == "High"`, enqueue a `CostAlert`.

### `alert_dispatcher.py`

**Trigger**: Queue — `cost-alerts` queue.

Logic flow:
1. Deserialise the queue message as a `CostAlert`.
2. Persist it to the Alerts table (for the API layer to query).
3. Call `AlertClient.send_slack()` and `AlertClient.send_teams()`.
4. Log success or failure for each channel.

**Interview point**: This is the one function that **does not** run on a timer.
It is event-driven from the queue, which means alerts are dispatched within
seconds of being enqueued — near real-time.

### `api_dashboard.py`

**Trigger**: HTTP — seven GET endpoints.

All endpoints follow the same pattern:
1. Read from Table Storage.
2. Aggregate/transform data in Python.
3. Return a JSON response.

Example — `/api/costs/by-team`:
```python
costs = storage.get_all(settings.COST_TABLE_NAME)
teams = {}
for c in costs:
    team = c.get("team", "unknown")
    teams[team] = teams.get(team, 0) + float(c.get("cost", 0))
```

**Interview point**: This aggregation runs in-memory in the Function.  For a
small-to-medium subscription this is fine.  For very large datasets, you would
consider:
- Materialised views (pre-computed aggregation tables).
- Moving to Cosmos DB with change feed for real-time rollups.
- Using Azure Data Explorer (Kusto) for analytical queries.

---

## 7. Azure Table Storage Design

### Why Table Storage?

| Consideration | Table Storage | Cosmos DB | SQL |
|---|---|---|---|
| Cost | Very low (~$0.045/GB/month) | Higher RU-based pricing | Higher |
| Schema | Schemaless | Schemaless | Schema-defined |
| Query | Filter by PartitionKey + RowKey | Full SQL-like queries | Full SQL |
| Scale | ~20k ops/sec per partition | Near-unlimited with partitioning | Depends on tier |
| Fit for this project | **Yes** — simple key-value with filters | Over-engineered | Over-engineered |

For a cost governance tool that writes a few hundred rows per day and serves
dashboard queries, Table Storage is the most cost-effective option.

### Table Schema

**DailyCosts**
```
PartitionKey: {subscription_id}_{date}     (e.g., "abc123_2024-01-15")
RowKey:       {resource_group}_{service}    (e.g., "rg-app-prod_Virtual Machines")
Fields:       cost (float), environment, team, service_name, resource_group, date
```

**WasteFindings**
```
PartitionKey: {subscription_id}
RowKey:       {sanitised_resource_id}
Fields:       resource_type, resource_name, resource_group, waste_type,
              estimated_monthly_savings, details
```

**AdvisorRecommendations**
```
PartitionKey: {subscription_id}
RowKey:       {recommendation_id}
Fields:       category, impact, impacted_resource, impacted_resource_type,
              description, estimated_annual_savings, action
```

**Alerts**
```
PartitionKey: {alert_type}    (e.g., "budget_exceeded", "waste_detected")
RowKey:       {timestamp}     (ISO 8601)
Fields:       severity, title, message, source
```

**Interview point**: The PartitionKey design ensures the most common query patterns
(get today's costs, get all waste, get recent alerts of a type) hit a single
partition — the fastest access pattern in Table Storage.

---

## 8. Alerting Pipeline — Queue Decoupling

### Why Not Send Alerts Directly?

The collector functions could call `AlertClient` directly.  But decoupling
through a queue provides:

| Benefit | Explanation |
|---|---|
| **Reliability** | If a webhook is down, the message stays in the queue and is retried automatically |
| **Speed** | Collector functions complete quickly — they don't wait for HTTP calls to Slack/Teams |
| **Scalability** | Multiple alert_dispatcher instances can process the queue in parallel |
| **Extensibility** | Adding email or PagerDuty requires only changes to the dispatcher, not to any collector |
| **Audit trail** | Every alert is persisted to the Alerts table regardless of webhook success |

### Queue Message Format

```json
{
  "alert_type": "budget_exceeded",
  "severity": "critical",
  "title": "Monthly budget exceeded",
  "message": "Current spend $12,450 exceeds budget of $10,000",
  "source": "cost_collector",
  "timestamp": "2024-01-15T06:02:30Z"
}
```

### Retry Behaviour

Azure Functions queue trigger has built-in retry with exponential backoff:
- 1st retry: ~10 seconds
- 2nd retry: ~30 seconds
- After 5 retries: message moves to `cost-alerts-poison` (dead-letter queue)

---

## 9. Azure Policy Governance

### What Are Azure Policies?

Azure Policy is a service that creates, assigns, and manages rules that resources
must follow.  Policies are evaluated on resource creation and updates.

### Policies in This Project

| Policy | Effect | Purpose |
|---|---|---|
| `require-environment-tag` | **Deny** | Block resource creation without `Environment` tag (must be dev/staging/prod) |
| `require-cost-center-tag` | **Deny** | Block resource creation without `CostCenter` tag |
| `require-owner-tag` | **Deny** | Block resource creation without `Owner` tag |
| `inherit-tags-from-rg` | **Modify** | Auto-copy `Environment`, `CostCenter`, `Owner` from resource group to resource |
| `policy-initiative` | (Set) | Bundles all policies for single-assignment management |

### Deny vs Modify

- **Deny**: Prevents the operation entirely. The user gets an error with the
  policy name and required field.
- **Modify**: Allows the operation but automatically adds/changes the specified
  fields.  Uses a **Managed Identity** (specified via `roleDefinitionIds`) to
  perform the modification.

**Interview point**: The combination is powerful — even if someone creates a
resource with the correct tags, the `Modify` policies ensure child resources
inherit their parent's tags.  This catches cases where ARM templates or Terraform
modules don't propagate tags down.

### Policy Initiative (Policy Set)

A Policy Initiative groups multiple policies into a single assignment.  Benefits:
- One assignment instead of five.
- Compliance dashboard shows initiative-level compliance %.
- Exemptions can be granted at the initiative level.

---

## 10. Logic Apps Notification Workflows

### Why Logic Apps Instead of Direct Webhooks?

| Factor | Direct webhook | Logic App |
|---|---|---|
| Retry logic | Must implement in code | Built-in with configurable retries |
| Rate limiting | Must implement in code | Configurable concurrency controls |
| Monitoring | Custom logging | Azure Portal run history |
| Transformation | Code-only | Designer visual editor |
| Secret management | In code/env vars | Managed by Logic App connections |

### Slack Workflow (`slack-notification.json`)

```
HTTP Request trigger
  → Parse JSON (validate schema)
    → Compose Slack message (mrkdwn blocks)
      → HTTP action (POST to Slack Incoming Webhook)
```

### Teams Workflow (`teams-notification.json`)

```
HTTP Request trigger
  → Parse JSON (validate schema)
    → Compose MessageCard
      → HTTP action (POST to Teams Incoming Webhook)
```

Both workflows expose an HTTP trigger URL.  The `alert_client.py` POSTs to these
URLs.  The Logic App handles delivery, retries, and logging.

---

## 11. Grafana Dashboards & Infinity Datasource

### Why Grafana?

- Open-source and free (Community Edition).
- Rich visualization library (gauges, time series, tables, pie charts).
- Supports many datasources — we use **Infinity** to query our HTTP API.
- Alerting built-in (though we handle alerts in the pipeline).

### Infinity Datasource

The **yesoreyeram-infinity-datasource** plugin lets Grafana query any HTTP/REST
endpoint returning JSON, CSV, XML, or GraphQL.  Configuration:

```yaml
datasources:
  - name: FinOps API
    type: yesoreyeram-infinity-datasource
    jsonData:
      url: http://localhost:7071  # Azure Functions local URL
```

Each panel specifies:
- `url`: e.g. `/api/costs/trends`
- `parser`: `backend` (server-side JSON parsing)
- `type`: `json`
- `root_selector`: JSONPath to the data array (e.g. `$.trends`)

### Dashboard: Cost Overview

7 panels:
1. **Monthly Budget Gauge** — Shows current spend vs budget (green/yellow/red).
2. **Total Monthly Spend** — Stat panel with large number.
3. **Active Cost Alerts** — Count of recent alerts.
4. **Daily Cost Trend** — Time series line chart over 30 days.
5. **Cost by Team** — Pie chart showing team breakdown.
6. **Cost by Environment** — Pie chart (dev vs staging vs prod).
7. **Cost by Service** — Top services bar chart.

### Dashboard: Waste Detection

6 panels:
1. **Total Potential Savings** — Stat (monthly $ savings if all waste is eliminated).
2. **Waste Finding Count** — How many wasteful resources found.
3. **Recommendation Count** — How many Advisor recommendations.
4. **Waste Findings Table** — Detailed table with resource, type, savings.
5. **Advisor Recommendations** — Table with description, impact, savings.
6. **Recent Alerts** — Table showing latest alert history.

---

## 12. Terraform Infrastructure-as-Code

### File Organisation

```
infra/terraform/
├── providers.tf       # azurerm provider + backend config
├── variables.tf       # All input variables with defaults
├── main.tf            # Resource group + shared locals
├── storage.tf         # Storage account, tables, queue
├── function_app.tf    # Consumption plan, Linux Function App, RBAC
├── logic_app.tf       # Logic App Standard workflows
├── monitoring.tf      # Log Analytics + Application Insights
├── policies.tf        # Policy definitions + assignments + initiative
└── outputs.tf         # Resource IDs, names, URLs
```

### Key Design Decisions

**1. Workspace-based environments**

Instead of duplicating entire Terraform directories for dev/staging/prod, we use
Terraform **workspaces**.  Each workspace maintains its own state:

```bash
terraform workspace new dev
terraform workspace new prod
terraform plan -var="environment=dev"
```

**2. Consumption Plan**

```hcl
resource "azurerm_service_plan" "this" {
  os_type  = "Linux"
  sku_name = "Y1"  # Consumption Plan
}
```

Y1 = Consumption.  This means:
- No charge when functions aren't running.
- Auto-scales based on queue depth / trigger load.
- Small cold start penalty (~2-5s for Python).

**3. Managed Identity + RBAC**

```hcl
resource "azurerm_linux_function_app" "this" {
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "reader" {
  principal_id = azurerm_linux_function_app.this.identity[0].principal_id
  role_definition_name = "Reader"
  scope = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
}

resource "azurerm_role_assignment" "cost_reader" {
  principal_id = azurerm_linux_function_app.this.identity[0].principal_id
  role_definition_name = "Cost Management Reader"
  scope = "/subscriptions/${data.azurerm_client_config.current.subscription_id}"
}
```

No keys or secrets are stored — the Function App authenticates to Azure services
using its system-assigned managed identity via `DefaultAzureCredential`.

**4. Remote State Backend**

```hcl
backend "azurerm" {
  resource_group_name  = "rg-terraform-state"
  storage_account_name = "stfinopstfstate"
  container_name       = "tfstate"
  key                  = "finops-cost-governance.tfstate"
}
```

State is stored in a separate Azure Storage Account (not managed by this
Terraform).  This prevents the chicken-and-egg problem and keeps state safe.

**5. Policy Definitions + Assignments + Initiative**

Terraform creates:
- 3 custom policy definitions (deny if tag missing).
- 3 built-in policy assignments (inherit tag from resource group — using
  `Microsoft.Authorization/policyDefinitions/...` built-in IDs).
- 1 policy set definition (initiative) that bundles them all.
- 1 policy assignment for the initiative at the resource group scope.

---

## 13. Security & Identity

### Authentication Chain

```
Azure Functions  →  DefaultAzureCredential  →  Managed Identity (in Azure)
                                            →  Azure CLI (local development)
```

`DefaultAzureCredential` tries multiple authentication methods in order:
1. Environment variables (CI/CD)
2. Managed Identity (Azure)
3. Azure CLI (local)
4. Visual Studio / VS Code credentials

This means the same code works in all environments without changes.

### Principle of Least Privilege

The Function App's Managed Identity has only two roles:
- **Reader**: Can list and inspect resources (needed for waste detection).
- **Cost Management Reader**: Can query cost data (needed for cost collection).

It **cannot** modify or delete any resources.

### Secret Management

| Secret | Storage Method |
|---|---|
| Storage connection string | Function App Application Settings (managed by Terraform) |
| Slack webhook URL | Function App Application Settings |
| Teams webhook URL | Function App Application Settings |
| Azure credentials | Managed Identity (no secret) |

No secrets are hard-coded in the repository.  The `.env.example` file documents
what is needed, but `.env` (with actual values) is in `.gitignore`.

---

## 14. Testing Strategy

### Test Pyramid

```
Integration Tests          ← 2 tests (full pipeline flow)
    ▲
Unit Tests                 ← 44 tests (individual functions)
    ▲
Type Safety / Linting      ← ruff (Python linter)
```

### What We Test

| Test File | Coverage |
|---|---|
| `test_models.py` | All 4 data models: construction, partition/row keys, to_entity, to_dict |
| `test_cost_collector.py` | CostClient query, anomaly detection, get_current_month_total |
| `test_resource_analyzer.py` | Each waste detection method, scan_all aggregation, helper functions |
| `test_recommendation_fetcher.py` | Advisor recommendation parsing, savings extraction |
| `test_alert_dispatcher.py` | Slack/Teams message formatting, HTTP webhook calls (mocked with `responses`) |
| `test_api_dashboard.py` | All 8 aggregation routes (summary, trends, by-team, etc.) |
| `test_integration.py` | End-to-end: cost collection → storage → alert dispatch |

### How We Mock

**Azure SDK mocks** — We use `unittest.mock.MagicMock` to replace SDK clients:
```python
@pytest.fixture
def mock_credential():
    return MagicMock()

# In tests:
client = CostClient(credential=mock_credential)
client._client.usage.query.return_value = mock_result
```

**HTTP mocks** — We use the `responses` library to intercept outgoing HTTP calls:
```python
@responses.activate
def test_send_slack():
    responses.add(responses.POST, "https://webhook.example.com/slack", status=200)
    client = AlertClient()
    client.send_slack(alert)
    assert len(responses.calls) == 1
```

**Storage mock** — The `conftest.py` provides a `mock_storage_client` that uses
an in-memory dictionary, so tests never touch Azurite or any real storage:
```python
@pytest.fixture
def mock_storage_client():
    store = {}
    client = MagicMock()
    def upsert(table, entities):
        store.setdefault(table, []).extend(entities)
        return len(entities)
    client.upsert_entities.side_effect = upsert
    # ...
```

### Why No Real Azure Calls in Tests?

1. **Speed**: Tests run in < 5 seconds total.
2. **Cost**: No Azure consumption.
3. **Reliability**: Tests never fail due to network issues or API rate limits.
4. **CI/CD**: Tests can run anywhere — no Azure account required.

---

## 15. Local Development Environment

### Docker Compose Stack

```yaml
services:
  azurite:                    # Azure Storage emulator
    image: mcr.microsoft.com/azure-storage/azurite
    ports: ["10000-10002"]    # Blob, Queue, Table endpoints

  grafana:                    # Dashboard server
    image: grafana/grafana:10.2.0
    ports: ["3000"]           # Web UI
    volumes:
      - ./dashboards/grafana/...  # Pre-provisioned dashboards + datasource
```

### Workflow

1. `docker-compose up -d` — starts Azurite (storage emulator) and Grafana.
2. `python scripts/seed_data.py` — populates Tables with realistic sample data.
3. `func start` (in the `functions/` directory) — runs Azure Functions locally.
4. Open `http://localhost:3000` — Grafana dashboards with live data.

The `.env.example` default storage connection string points to Azurite:
```
DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=...;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
```

---

## 16. Deployment Flow

```
Developer machine
  │
  ├─ terraform init / plan / apply   → Creates Azure infrastructure
  │                                     (Resource Group, Storage, Function App,
  │                                      Logic Apps, Policies, Monitoring)
  │
  └─ func azure functionapp publish  → Deploys Python code to Function App
```

The `scripts/deploy.sh` script automates this:
1. Validates prerequisites (az, terraform, func CLI).
2. Runs `terraform init` + `plan` + `apply`.
3. Captures `function_app_name` from Terraform outputs.
4. Runs `func azure functionapp publish`.

---

## 17. Design Decisions & Trade-offs

### Decision 1: Azure Functions vs Container Apps

**Chose**: Azure Functions (Consumption Plan)

| Factor | Functions | Container Apps |
|---|---|---|
| Cost model | Per-execution (ideal for daily timers) | Per-vCPU-second |
| Management | Fully managed | Semi-managed |
| Cold starts | Yes (~2-5s Python) | Optional (minimum replicas) |
| Fit for timer workloads | Excellent | Over-engineered |

Functions win because our workload is 3 daily timer executions + occasional HTTP
requests.  Container Apps would be cheaper only at sustained high throughput.

### Decision 2: Table Storage vs Cosmos DB

**Chose**: Azure Table Storage

For a cost governance tool writing hundreds of rows per day, Table Storage costs
pennies.  Cosmos DB would add complexity (RU budgeting, partition design) without
benefit at this scale.

### Decision 3: Grafana vs Power BI

**Chose**: Grafana

- Free (Community Edition).
- Declarative provisioning (dashboards are JSON files in git).
- Engineer-friendly.
- Infinity datasource can query any HTTP API.

Power BI would require licenses and doesn't support declarative provisioning as
cleanly.

### Decision 4: Queue-decoupled alerts vs direct dispatch

**Chose**: Queue-decoupled

See [Section 8](#8-alerting-pipeline--queue-decoupling) for full reasoning.  The
key benefit is reliability — even if Slack is down, alerts are persisted and
retried.

### Decision 5: Blueprint pattern vs one-file functions

**Chose**: Blueprints

- Better separation of concerns.
- Each function has its own test file.
- Easier to add new functions without modifying existing code.

---

## 18. Interview Questions & Answers

### Q1: Walk me through the architecture.

**A**: The system has five Azure Functions on a Consumption Plan.  Three timer
functions run daily to collect cost data (from Cost Management API), detect
wasted resources (via Compute/Network SDKs), and fetch Advisor recommendations.
All data is stored in Azure Table Storage.  When anomalies or threshold breaches
are detected, CostAlert messages are enqueued to a Storage Queue.  A fourth
function (queue-triggered) dispatches these alerts to Slack and Teams via Logic
App webhooks.  A fifth function exposes seven HTTP endpoints that Grafana
dashboards query via the Infinity datasource.  Azure Policy enforces tag
governance.  Everything is provisioned with Terraform.

### Q2: Why did you choose Azure Functions over Kubernetes or Container Apps?

**A**: The workload is three daily timer executions and low-frequency HTTP
requests. Functions on a Consumption Plan cost nearly zero for this usage
pattern.  Container Apps or AKS would introduce operational overhead
(container image management, scaling configuration) without any benefit at
this scale.

### Q3: How do you handle secrets?

**A**: There are no secrets in the codebase.  The Function App uses a
system-assigned Managed Identity to authenticate to Azure APIs via
`DefaultAzureCredential`.  Webhook URLs and the storage connection string are
stored as Function App Application Settings, provisioned by Terraform.
The `.env` file (for local dev) is gitignored.

### Q4: What happens if Slack is down when an alert fires?

**A**: The alert is enqueued to a Storage Queue.  The `alert_dispatcher`
function processes it and attempts to POST to Slack.  If the POST fails,
the message stays in the queue and Azure Functions retries it with exponential
backoff (5 attempts).  After all retries, it goes to the `cost-alerts-poison`
dead-letter queue.  Meanwhile, the alert is **always persisted** to the
Alerts table regardless of webhook success, so it's visible in the dashboard.

### Q5: How do you detect cost anomalies?

**A**: The `cost_collector` calculates the total cost for today vs yesterday.
If today's cost exceeds yesterday's by more than the configured percentage
threshold (default 25%), it's flagged as an anomaly.  This is a simple
day-over-day comparison.  For production, you might add a rolling 7-day
average or standard deviation model.

### Q6: Explain your Table Storage partition key design.

**A**: DailyCosts uses `{subscription}_{date}` as partition key, so querying
"all costs for today" hits a single partition.  WasteFindings and Advisor
Recommendations use `{subscription}` because the full dataset is small and
always queried together.  Alerts use `{alert_type}` for efficient filtering by
type (budget exceeded vs waste detected).

### Q7: Why use a Policy Initiative instead of individual policy assignments?

**A**: An initiative bundles all five governance policies into one assignment.
This means one compliance score to track, one exemption to manage, and one
remediation task to run.  It simplifies management and aligns with Azure
Well-Architected Framework guidance for policy-at-scale.

### Q8: How would you scale this for 100 subscriptions?

**A**: Several changes:
1. Parameterize the subscription ID — iterate over a list of subscriptions.
2. Increase the timer function timeout or split into per-subscription instances.
3. Consider moving from Table Storage to Cosmos DB for higher throughput.
4. Add Managed Identity Reader roles on all target subscriptions.
5. Use Azure Lighthouse for multi-tenant visibility.

### Q9: What's the testing approach?

**A**: 44+ unit tests and 2 integration tests.  All Azure SDK calls are mocked
with `unittest.mock.MagicMock`.  HTTP calls (webhooks) are mocked with the
`responses` library.  Table Storage is mocked with an in-memory dictionary.
Tests run in < 5 seconds with no Azure account required.  We also use `ruff`
for linting.

### Q10: How do you ensure tag governance is enforced?

**A**: Azure Policy with `Deny` effect prevents resource creation without
required tags (`Environment`, `CostCenter`, `Owner`).  `Modify` effect policies
auto-inherit tags from resource groups to child resources.  These are grouped
into an initiative and assigned at the resource group level via Terraform.
Compliance is visible in the Azure Portal compliance dashboard.

### Q11: What is `DefaultAzureCredential` and why is it important?

**A**: `DefaultAzureCredential` is from the `azure-identity` SDK.  It tries
multiple authentication methods in sequence: environment variables, managed
identity, Azure CLI, and more.  This means the same code works in local
development (Azure CLI), CI/CD (environment variables), and production
(managed identity) without code changes.

### Q12: How does the Grafana Infinity datasource work?

**A**: Infinity is a Grafana plugin that can query any REST API.  Each dashboard
panel is configured with a URL pointing to our Function App HTTP endpoints
(e.g. `/api/costs/trends`).  The plugin fetches the JSON response and maps
the returned array to Grafana's table/time-series data format.  This avoids
needing a dedicated database datasource in Grafana.

### Q13: Walk me through a cost alert end-to-end.

**A**: At 06:00 UTC the `cost_collector` timer fires.  It queries Azure Cost
Management for the day's costs.  Suppose today's total is $1,500 and
yesterday was $1,000 — a 50% increase exceeds the 25% threshold.  The function
creates a `CostAlert(type="daily_anomaly", severity="warning", ...)` and
serialises it to a Storage Queue message.  Within seconds the
`alert_dispatcher` queue trigger fires, deserialises the alert, persists it
to the Alerts table, and POSTs formatted messages to both the Slack and Teams
Logic App webhooks.  The Logic Apps deliver the messages to the respective
channels.  The alert is also visible in Grafana via `/api/alerts/recent`.

### Q14: Why not use Azure Monitor Alerts instead of building your own?

**A**: Azure Monitor Alerts work well for infrastructure metrics, but they
don't provide custom cost anomaly detection, waste scanning, or team-level
attribution.  Our pipeline gives us full control over:
- Detection logic (custom thresholds, day-over-day comparison).
- Message formatting (Slack markdown, Teams card format).
- Data aggregation (by team, environment, service).
- Historical storage (every alert persisted for trending).

That said, we **do** use App Insights and Log Analytics for monitoring the
Functions themselves.

### Q15: What would you change for a production deployment?

**A**:
1. **Authentication**: Add Function-level API keys or Azure AD auth on HTTP endpoints.
2. **Anomaly detection**: Replace simple day-over-day with statistical model (ARIMA, z-score).
3. **Multi-subscription**: Support iterating over multiple subscriptions.
4. **Error handling**: Add circuit breakers for webhook calls.
5. **State management**: Consider Cosmos DB if data volume grows significantly.
6. **CI/CD**: GitHub Actions pipeline for Terraform + Function deployment.
7. **Secrets**: Store webhook URLs in Key Vault instead of app settings.
8. **Dashboard auth**: Add Grafana Azure AD integration for SSO.
