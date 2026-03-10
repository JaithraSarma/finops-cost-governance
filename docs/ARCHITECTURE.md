# Architecture

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Azure Cloud                               │
│                                                                     │
│  ┌──────────────┐   Timer Triggers    ┌──────────────────────────┐ │
│  │ Azure Cost   │ ──────────────────► │  Azure Functions         │ │
│  │ Management   │                     │  (Consumption Plan)      │ │
│  │ API          │                     │                          │ │
│  ├──────────────┤                     │  ┌────────────────────┐  │ │
│  │ Compute /    │ ◄─────────────────► │  │ cost_collector     │  │ │
│  │ Network /    │                     │  │ resource_analyzer  │  │ │
│  │ Resource     │                     │  │ recommendation_    │  │ │
│  │ SDKs         │                     │  │    fetcher         │  │ │
│  ├──────────────┤                     │  │ alert_dispatcher   │  │ │
│  │ Azure        │                     │  │ api_dashboard      │  │ │
│  │ Advisor      │                     │  └────────────────────┘  │ │
│  └──────────────┘                     └──────────┬───────────────┘ │
│                                                  │                  │
│                        ┌─────────────────────────┼─────────────┐   │
│                        │                         │             │   │
│                        ▼                         ▼             ▼   │
│               ┌────────────────┐   ┌───────────────┐  ┌────────┐ │
│               │ Azure Table    │   │ Storage Queue  │  │ Logic  │ │
│               │ Storage        │   │ (cost-alerts)  │  │ Apps   │ │
│               │                │   └───────┬───────┘  │        │ │
│               │ • DailyCosts   │           │          │ Slack  │ │
│               │ • WasteFindings│           │          │ Teams  │ │
│               │ • Advisor Recs │           ▼          └────────┘ │
│               │ • Alerts       │   alert_dispatcher               │
│               └────────────────┘                                   │
│                        │                                           │
│                        │  HTTP API (/api/*)                        │
│                        ▼                                           │
│               ┌────────────────┐                                   │
│               │ Grafana        │    ← Infinity datasource          │
│               │ Dashboards     │                                   │
│               └────────────────┘                                   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Azure Policy (Governance Layer)                             │  │
│  │  • require-environment-tag   • inherit-tags-from-rg          │  │
│  │  • require-cost-center-tag   • policy-initiative             │  │
│  │  • require-owner-tag                                         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Terraform (Infrastructure as Code)                          │  │
│  │  Resource Group · Storage · Function App · Logic Apps        │  │
│  │  Log Analytics · App Insights · Policies                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Deep-Dive

### 1. Data Collection Layer

| Function | Trigger | Schedule | Purpose |
|---|---|---|---|
| `cost_collector` | Timer | 06:00 UTC daily | Queries Azure Cost Management for daily costs |
| `resource_analyzer` | Timer | 07:00 UTC daily | Scans for wasted resources (disks, IPs, LBs, VMs) |
| `recommendation_fetcher` | Timer | 08:00 UTC daily | Pulls Azure Advisor cost recommendations |

The sequential scheduling (06 → 07 → 08) prevents API throttling and ensures
costs are available before waste analysis runs.

### 2. Alerting Pipeline

```
Timer Functions ─── detect anomaly / threshold ──► Storage Queue
                                                        │
                                                        ▼
                                              alert_dispatcher (queue trigger)
                                                        │
                                              ┌─────────┴──────────┐
                                              ▼                    ▼
                                        Slack Webhook        Teams Webhook
                                       (Logic App)          (Logic App)
```

**Decoupled by design**: Data collectors enqueue `CostAlert` messages instead
of sending notifications directly.  This means:

- Collection functions always complete quickly.
- Alert dispatch can be retried independently.
- Adding a new notification channel (email, PagerDuty) requires zero changes
  to the collectors.

### 3. Dashboard API Layer

The `api_dashboard` blueprint exposes seven HTTP endpoints that serve as a
read-only API over the Table Storage data:

| Endpoint | Description |
|---|---|
| `GET /api/health` | Health check (returns 200 with status) |
| `GET /api/costs/summary` | Total spend, record count, average daily cost |
| `GET /api/costs/trends` | Daily cost time-series for charting |
| `GET /api/costs/by-team` | Costs aggregated by team tag |
| `GET /api/costs/by-environment` | Costs aggregated by environment tag |
| `GET /api/waste/report` | All waste findings + total potential savings |
| `GET /api/recommendations` | Advisor recommendations |
| `GET /api/alerts/recent` | Recent alert history |

Grafana's **Infinity** datasource fetches JSON from these endpoints so that
no direct database access is required from the dashboard layer.

### 4. Governance Layer (Azure Policy)

Five policy definitions enforce tagging discipline across the subscription:

- **Deny** resources without `Environment`, `CostCenter`, or `Owner` tags.
- **Modify** new resources to inherit tags from their parent resource group.
- All bundled into a **Policy Initiative** for single-assignment deployment.

### 5. Infrastructure as Code (Terraform)

All resources are managed through Terraform with workspace-based environment
separation (`dev`, `staging`, `prod`).

Key design decisions:
- **Consumption Plan** for Functions (pay-per-execution, no idle cost).
- **System-assigned Managed Identity** with `Reader` + `Cost Management Reader`
  roles — no secrets stored.
- **azurerm backend** for remote state with a separate state storage account.

## Data Flow

```
1.  06:00 UTC ─ cost_collector
    │   Azure Cost Management API → daily cost rows
    │   → upsert into DailyCosts table
    │   → check monthly budget → CostAlert if exceeded
    │   → check daily anomaly → CostAlert if spike detected
    │
2.  07:00 UTC ─ resource_analyzer
    │   Compute SDK → unattached disks, oversized VMs
    │   Network SDK → idle load balancers, unused public IPs
    │   → upsert into WasteFindings table
    │   → CostAlert with waste summary
    │
3.  08:00 UTC ─ recommendation_fetcher
    │   Advisor SDK → cost-category recommendations
    │   → upsert into AdvisorRecommendations table
    │   → CostAlert for high-impact items
    │
4.  On-demand ─ alert_dispatcher (queue trigger)
    │   Dequeue CostAlert message
    │   → persist to Alerts table
    │   → POST to Slack Logic App webhook
    │   → POST to Teams Logic App webhook
    │
5.  Any time ─ api_dashboard (HTTP trigger)
        Read tables → aggregate → return JSON → Grafana renders
```

## Security Model

- **No stored credentials**: Functions use `DefaultAzureCredential` (Managed
  Identity in Azure, Azure CLI locally).
- **Least-privilege RBAC**: Reader + Cost Management Reader only.
- **Logic App webhooks**: Triggered by Functions, external webhook URLs stored
  as Function App application settings (not in code).
- **Table Storage**: Access via connection string stored in Function App
  settings; no public access enabled.
