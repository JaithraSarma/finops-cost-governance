# ─────────────────────────────────────────────────────────────
# Main — Resource Group & naming convention
# ─────────────────────────────────────────────────────────────

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  common_tags = merge(var.tags, {
    environment  = var.environment
    cost-center  = "platform-engineering"
  })
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.common_tags
}
