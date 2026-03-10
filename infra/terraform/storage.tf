# ─────────────────────────────────────────────────────────────
# Azure Storage Account — Table Storage for cost data + Function App
# ─────────────────────────────────────────────────────────────

resource "azurerm_storage_account" "main" {
  name                     = "st${replace(local.name_prefix, "-", "")}data"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
  tags                     = local.common_tags
}

# Storage tables for governance data
resource "azurerm_storage_table" "cost_records" {
  name                 = "CostRecords"
  storage_account_name = azurerm_storage_account.main.name
}

resource "azurerm_storage_table" "waste_resources" {
  name                 = "WasteResources"
  storage_account_name = azurerm_storage_account.main.name
}

resource "azurerm_storage_table" "recommendations" {
  name                 = "Recommendations"
  storage_account_name = azurerm_storage_account.main.name
}

resource "azurerm_storage_table" "alerts" {
  name                 = "Alerts"
  storage_account_name = azurerm_storage_account.main.name
}

# Queue for alert dispatching
resource "azurerm_storage_queue" "cost_alerts" {
  name                 = "cost-alerts"
  storage_account_name = azurerm_storage_account.main.name
}
