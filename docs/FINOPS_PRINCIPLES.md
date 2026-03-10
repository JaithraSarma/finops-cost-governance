# FinOps Principles

This project is built around the **FinOps Foundation** framework for cloud
financial management.  Below is a mapping of FinOps principles to the features
implemented in this codebase.

---

## 1. Teams Need to Collaborate

| Principle | Implementation |
|---|---|
| Shared cost visibility | Grafana dashboards accessible by engineering, finance, and leadership |
| Team-level attribution | Every cost record carries `team` and `environment` tags |
| Multi-channel alerts | Slack + Teams notifications ensure the right people see anomalies |

## 2. Everyone Takes Ownership

| Principle | Implementation |
|---|---|
| Mandatory tagging | Azure Policy **denies** resource creation without `Owner`, `CostCenter`, `Environment` |
| Tag inheritance | Resources automatically inherit tags from their parent resource group |
| Self-service dashboards | HTTP API enables any team to build their own views |

## 3. A Centralized Team Drives FinOps

| Principle | Implementation |
|---|---|
| Single source of truth | Azure Table Storage holds all cost, waste, recommendation, and alert data |
| Automated collection | Timer-triggered functions run daily — no manual data gathering |
| Consistent policies | Policy Initiative bundles all governance rules for single-click enforcement |

## 4. Reports Should Be Accessible and Timely

| Principle | Implementation |
|---|---|
| Daily refresh | Cost collector runs every 24 hours at 06:00 UTC |
| Real-time alerts | Queue-triggered dispatcher sends alerts within seconds of detection |
| Drill-down capability | API endpoints support filtering by team, environment, resource group |

## 5. Decisions Are Driven by the Business Value of Cloud

| Principle | Implementation |
|---|---|
| Cost vs value | Advisor recommendations include estimated annual savings |
| Waste identification | Resource analyzer highlights idle/orphaned resources with $ impact |
| Budget tracking | Monthly budget threshold triggers proactive alerts |

## 6. Take Advantage of the Variable Cost Model

| Principle | Implementation |
|---|---|
| Right-sizing | Resource analyzer detects oversized VMs (avg CPU < threshold) |
| Reserved instance guidance | Advisor recommendations surface RI opportunities |
| Consumption-based hosting | The Function App itself runs on a Consumption Plan |

---

## FinOps Lifecycle Mapping

```
         ┌──────────┐
         │  Inform   │ ◄── cost_collector, api_dashboard, Grafana
         └────┬─────┘
              │
              ▼
         ┌──────────┐
         │ Optimize  │ ◄── resource_analyzer, recommendation_fetcher
         └────┬─────┘
              │
              ▼
         ┌──────────┐
         │  Operate  │ ◄── alert_dispatcher, Azure Policy, Terraform
         └──────────┘
```

- **Inform**: Collect data, build dashboards, make cost visible.
- **Optimize**: Identify savings, right-size, eliminate waste.
- **Operate**: Enforce governance, automate responses, iterate.
