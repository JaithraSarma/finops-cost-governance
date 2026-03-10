# ─────────────────────────────────────────────────────────────
# Azure Policy — Tagging governance
# ─────────────────────────────────────────────────────────────

# Policy: Require 'environment' tag on resource groups
resource "azurerm_policy_definition" "require_env_tag" {
  name         = "require-environment-tag"
  policy_type  = "Custom"
  mode         = "All"
  display_name = "Require 'environment' tag on Resource Groups"
  description  = "Denies creation of resource groups without an 'environment' tag with an allowed value."

  metadata = jsonencode({ category = "Tags" })

  policy_rule = jsonencode({
    if = {
      allOf = [
        { field = "type", equals = "Microsoft.Resources/subscriptions/resourceGroups" },
        {
          not = {
            field = "tags['environment']"
            in    = ["dev", "staging", "prod", "sandbox", "shared"]
          }
        }
      ]
    }
    then = { effect = "deny" }
  })
}

# Policy: Require 'cost-center' tag on resource groups
resource "azurerm_policy_definition" "require_cc_tag" {
  name         = "require-cost-center-tag"
  policy_type  = "Custom"
  mode         = "All"
  display_name = "Require 'cost-center' tag on Resource Groups"
  description  = "Denies creation of resource groups without a 'cost-center' tag."

  metadata = jsonencode({ category = "Tags" })

  policy_rule = jsonencode({
    if = {
      allOf = [
        { field = "type", equals = "Microsoft.Resources/subscriptions/resourceGroups" },
        { field = "tags['cost-center']", exists = false }
      ]
    }
    then = { effect = "deny" }
  })
}

# Policy: Require 'owner' tag on resource groups
resource "azurerm_policy_definition" "require_owner_tag" {
  name         = "require-owner-tag"
  policy_type  = "Custom"
  mode         = "All"
  display_name = "Require 'owner' tag on Resource Groups"
  description  = "Denies creation of resource groups without an 'owner' tag."

  metadata = jsonencode({ category = "Tags" })

  policy_rule = jsonencode({
    if = {
      allOf = [
        { field = "type", equals = "Microsoft.Resources/subscriptions/resourceGroups" },
        { field = "tags['owner']", exists = false }
      ]
    }
    then = { effect = "deny" }
  })
}

# Policy: Inherit tags from resource group (using built-in)
resource "azurerm_subscription_policy_assignment" "inherit_env_tag" {
  name                 = "inherit-environment-tag"
  subscription_id      = data.azurerm_subscription.current.id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/cd3aa116-8754-49c9-a813-ad46512ece54"
  display_name         = "Inherit 'environment' tag from resource group"

  parameters = jsonencode({
    tagName = { value = "environment" }
  })

  identity {
    type = "SystemAssigned"
  }
  location = var.location
}

resource "azurerm_subscription_policy_assignment" "inherit_cc_tag" {
  name                 = "inherit-cost-center-tag"
  subscription_id      = data.azurerm_subscription.current.id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/cd3aa116-8754-49c9-a813-ad46512ece54"
  display_name         = "Inherit 'cost-center' tag from resource group"

  parameters = jsonencode({
    tagName = { value = "cost-center" }
  })

  identity {
    type = "SystemAssigned"
  }
  location = var.location
}

resource "azurerm_subscription_policy_assignment" "inherit_owner_tag" {
  name                 = "inherit-owner-tag"
  subscription_id      = data.azurerm_subscription.current.id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/cd3aa116-8754-49c9-a813-ad46512ece54"
  display_name         = "Inherit 'owner' tag from resource group"

  parameters = jsonencode({
    tagName = { value = "owner" }
  })

  identity {
    type = "SystemAssigned"
  }
  location = var.location
}

# Policy Initiative (Policy Set) — bundle all tagging policies
resource "azurerm_policy_set_definition" "tagging_initiative" {
  name         = "finops-tagging-governance"
  policy_type  = "Custom"
  display_name = "FinOps Tagging Governance Initiative"
  description  = "Bundles all required tag policies for cost governance."

  metadata = jsonencode({ category = "Tags" })

  policy_definition_reference {
    policy_definition_id = azurerm_policy_definition.require_env_tag.id
    reference_id         = "requireEnvironmentTag"
  }

  policy_definition_reference {
    policy_definition_id = azurerm_policy_definition.require_cc_tag.id
    reference_id         = "requireCostCenterTag"
  }

  policy_definition_reference {
    policy_definition_id = azurerm_policy_definition.require_owner_tag.id
    reference_id         = "requireOwnerTag"
  }
}
