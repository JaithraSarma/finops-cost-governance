# ─────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────

output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "function_app_name" {
  value = azurerm_linux_function_app.main.name
}

output "function_app_url" {
  value = "https://${azurerm_linux_function_app.main.default_hostname}"
}

output "function_app_identity_id" {
  value = azurerm_linux_function_app.main.identity[0].principal_id
}

output "storage_account_name" {
  value = azurerm_storage_account.main.name
}

output "logic_app_slack_url" {
  value     = azurerm_logic_app_trigger_http_request.slack_trigger.callback_url
  sensitive = true
}

output "logic_app_teams_url" {
  value     = azurerm_logic_app_trigger_http_request.teams_trigger.callback_url
  sensitive = true
}

output "application_insights_name" {
  value = azurerm_application_insights.main.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}
