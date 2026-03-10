# ─────────────────────────────────────────────────────────────
# Azure Function App — Python v2 (Consumption plan)
# ─────────────────────────────────────────────────────────────

resource "azurerm_service_plan" "functions" {
  name                = "asp-${local.name_prefix}-functions"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption plan
  tags                = local.common_tags
}

resource "azurerm_linux_function_app" "main" {
  name                       = "func-${local.name_prefix}-governance"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.main.name
  storage_account_access_key = azurerm_storage_account.main.primary_access_key
  tags                       = local.common_tags

  site_config {
    application_stack {
      python_version = "3.11"
    }
    application_insights_connection_string = azurerm_application_insights.main.connection_string
    application_insights_key               = azurerm_application_insights.main.instrumentation_key
  }

  app_settings = {
    "FUNCTIONS_WORKER_RUNTIME"              = "python"
    "AzureWebJobsFeatureFlags"              = "EnableWorkerIndexing"
    "AZURE_SUBSCRIPTION_ID"                 = data.azurerm_subscription.current.subscription_id
    "STORAGE_CONNECTION_STRING"             = azurerm_storage_account.main.primary_connection_string
    "LOGIC_APP_SLACK_WEBHOOK_URL"           = var.slack_webhook_url
    "LOGIC_APP_TEAMS_WEBHOOK_URL"           = var.teams_webhook_url
    "DAILY_BUDGET_LIMIT"                    = tostring(var.daily_budget_limit)
    "MONTHLY_BUDGET_LIMIT"                  = tostring(var.monthly_budget_limit)
    "COST_ANOMALY_THRESHOLD_PERCENT"        = tostring(var.cost_anomaly_threshold_percent)
  }

  identity {
    type = "SystemAssigned"
  }
}

data "azurerm_subscription" "current" {}

# Grant the Function App's managed identity read access to the subscription
# for querying Cost Management, Compute, Network, Advisor, and Monitor APIs
resource "azurerm_role_assignment" "func_reader" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Reader"
  principal_id         = azurerm_linux_function_app.main.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_cost_reader" {
  scope                = data.azurerm_subscription.current.id
  role_definition_name = "Cost Management Reader"
  principal_id         = azurerm_linux_function_app.main.identity[0].principal_id
}
