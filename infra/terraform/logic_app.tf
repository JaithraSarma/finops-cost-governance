# ─────────────────────────────────────────────────────────────
# Logic Apps — Slack & Teams notification workflows
# ─────────────────────────────────────────────────────────────

resource "azurerm_logic_app_workflow" "slack" {
  name                = "logic-${local.name_prefix}-slack"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags
}

resource "azurerm_logic_app_trigger_http_request" "slack_trigger" {
  name         = "slack-http-trigger"
  logic_app_id = azurerm_logic_app_workflow.slack.id
  schema       = <<-SCHEMA
    {
      "type": "object",
      "properties": {
        "text": { "type": "string" }
      },
      "required": ["text"]
    }
  SCHEMA
}

resource "azurerm_logic_app_workflow" "teams" {
  name                = "logic-${local.name_prefix}-teams"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = local.common_tags
}

resource "azurerm_logic_app_trigger_http_request" "teams_trigger" {
  name         = "teams-http-trigger"
  logic_app_id = azurerm_logic_app_workflow.teams.id
  schema       = <<-SCHEMA
    {
      "type": "object",
      "properties": {
        "@type": { "type": "string" },
        "summary": { "type": "string" },
        "sections": { "type": "array" }
      }
    }
  SCHEMA
}
