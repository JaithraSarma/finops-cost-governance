# FinOps Cost Governance & Optimization Dashboard

**Automated cloud cost visibility, waste detection, and governance for Azure subscriptions.**

---

## Overview

This project implements a complete FinOps cost governance pipeline on Azure using serverless architecture. Five Azure Functions collect cost data, detect wasted resources, fetch optimization recommendations, dispatch alerts, and serve a dashboard API — all backed by Azure Table Storage, Logic Apps for notifications, Grafana for visualization, Azure Policy for tag governance, and Terraform for infrastructure-as-code.

### Key Capabilities

- **Daily Cost Collection** — Queries Azure Cost Management API, stores daily cost records, detects budget overruns and spending anomalies.
- **Waste Detection** — Scans for unattached disks, unused public IPs, idle load balancers, and oversized virtual machines.
- **Advisor Recommendations** — Pulls Azure Advisor cost-category recommendations with estimated annual savings.
- **Multi-Channel Alerting** — Queue-decoupled alert pipeline dispatches to both Slack and Microsoft Teams via Logic App webhooks.
- **Dashboard API** — Seven HTTP endpoints serve aggregated cost, waste, recommendation, and alert data for Grafana dashboards.
- **Tag Governance** — Azure Policy definitions deny untagged resources and auto-inherit tags from resource groups.
- **Full IaC** — Terraform manages the entire infrastructure (Function App, Storage, Logic Apps, Policies, Monitoring).

---

## Architecture

```
Azure Cost Management ─┐
Azure Compute SDK     ─┤   Timer Triggers    ┌─────────────────────┐
Azure Network SDK     ─┼──────────────────►  │  Azure Functions    │
Azure Advisor SDK     ─┘                     │  (Python 3.11)      │
                                             │                     │
                                             │  cost_collector     │
                                             │  resource_analyzer  │
                                             │  recommendation_    │
                                             │      fetcher        │
                                             │  alert_dispatcher   │
                                             │  api_dashboard      │
                                             └──────┬──────────────┘
                                                    │
                              ┌──────────────┬──────┼──────────┐
                              ▼              ▼      ▼          ▼
                       Table Storage    Storage Queue    Logic Apps
                       (4 tables)      (cost-alerts)    (Slack/Teams)
                              │
                              ▼
                        Grafana Dashboards
                       (Infinity datasource)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full component deep-dive.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Compute | Azure Functions (Python v2, Consumption Plan) |
| Storage | Azure Table Storage |
| Messaging | Azure Storage Queue |
| Notifications | Azure Logic Apps → Slack / Teams |
| Dashboards | Grafana 10.2 + Infinity datasource |
| Governance | Azure Policy (Deny + Modify effects) |
| IaC | Terraform (~3.85 azurerm provider) |
| Monitoring | Azure Log Analytics + Application Insights |
| Auth | Managed Identity + DefaultAzureCredential |
| Testing | pytest + responses |
| Local Dev | Docker Compose (Azurite + Grafana) |

---

## Project Structure

```
finops-cost-governance/
├── functions/                  # Azure Functions application
│   ├── function_app.py         # Entry point — registers all blueprints
│   ├── host.json               # Runtime configuration
│   ├── requirements.txt        # Function-specific dependencies
│   ├── shared/                 # Shared modules
│   │   ├── config.py           # Settings from environment variables
│   │   ├── models.py           # Data classes (CostRecord, WasteResource, etc.)
│   │   ├── cost_client.py      # Azure Cost Management wrapper
│   │   ├── resource_client.py  # VM / Disk / IP / LB scanner
│   │   ├── advisor_client.py   # Azure Advisor wrapper
│   │   ├── alert_client.py     # Slack & Teams webhook dispatcher
│   │   └── storage_client.py   # Azure Table Storage CRUD wrapper
│   └── blueprints/             # Function blueprints (one per concern)
│       ├── cost_collector.py
│       ├── resource_analyzer.py
│       ├── recommendation_fetcher.py
│       ├── alert_dispatcher.py
│       └── api_dashboard.py
├── policies/                   # Azure Policy JSON definitions
├── logic-apps/                 # Logic App workflow definitions
├── dashboards/grafana/         # Grafana provisioning & dashboard JSON
├── infra/terraform/            # Terraform IaC (9 files)
├── scripts/
│   ├── setup.sh                # Bootstrap local dev environment
│   ├── deploy.sh               # Deploy infra + functions to Azure
│   └── seed_data.py            # Populate tables with sample data
├── tests/                      # pytest suite (unit + integration)
├── docs/
│   ├── ARCHITECTURE.md         # Component deep-dive
│   └── FINOPS_PRINCIPLES.md    # FinOps framework mapping
├── docker-compose.yml          # Local Azurite + Grafana
├── requirements.txt            # Top-level Python dependencies
├── Makefile                    # Dev workflow shortcuts
└── .env.example                # Required environment variables
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Azure CLI (`az`)
- Azure Functions Core Tools (`func`)
- Terraform 1.x

### Local Development

```bash
# 1. Clone and set up
git clone https://github.com/JaithraSarma/finops-cost-governance.git
cd finops-cost-governance
bash scripts/setup.sh

# 2. Edit environment variables
cp .env.example .env
# Add your AZURE_SUBSCRIPTION_ID (or leave defaults for local-only testing)

# 3. Start local services
docker-compose up -d      # Azurite + Grafana

# 4. Seed sample data
make seed

# 5. Run tests
make test

# 6. Open Grafana
# http://localhost:3000 (admin / admin)
```

### Deploy to Azure

```bash
# Ensure you are logged in
az login

# Deploy infrastructure + functions
bash scripts/deploy.sh dev
```

---

## Makefile Targets

| Command | Description |
|---|---|
| `make install` | Create venv and install dependencies |
| `make test` | Run full pytest suite |
| `make lint` | Run ruff linter |
| `make seed` | Seed Table Storage with sample data |
| `make docker-up` | Start Azurite + Grafana |
| `make docker-down` | Stop containers |
| `make deploy` | Deploy to Azure (Terraform + Functions) |
| `make clean` | Remove .venv, caches, Terraform state |

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `AZURE_SUBSCRIPTION_ID` | Target Azure subscription | — |
| `AZURE_STORAGE_CONNECTION_STRING` | Storage connection string | Azurite default |
| `SLACK_WEBHOOK_URL` | Logic App Slack webhook URL | — |
| `TEAMS_WEBHOOK_URL` | Logic App Teams webhook URL | — |
| `MONTHLY_BUDGET_USD` | Monthly budget threshold | 10000 |
| `DAILY_ANOMALY_THRESHOLD_PCT` | Daily cost spike % | 25 |
| `LOOKBACK_DAYS` | Cost query lookback window | 30 |

See [.env.example](.env.example) for the full list.

---

## Testing

```bash
make test
# or
python -m pytest tests/ -v
```

The test suite covers:
- **Data models** — Serialization, partition/row keys, entity conversion
- **Cost client** — Query construction and anomaly detection
- **Resource analyzer** — Disk, IP, LB, VM waste detection
- **Advisor client** — Recommendation parsing and savings extraction
- **Alert dispatcher** — Slack/Teams webhook formatting and dispatch
- **Dashboard API** — Aggregation logic for all HTTP endpoints
- **Integration** — End-to-end pipeline flow

All external Azure SDK calls are mocked — no Azure account required to run tests.

---

## License

MIT
