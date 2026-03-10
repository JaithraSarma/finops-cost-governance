#!/usr/bin/env bash
# deploy.sh — Deploy FinOps infrastructure and Azure Functions to Azure
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# ── Helpers ──────────────────────────────────────────────────────────────────
info()  { echo "[INFO]  $*"; }
error() { echo "[ERROR] $*" >&2; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────────────────────
command -v az       &>/dev/null || error "Azure CLI (az) is required."
command -v terraform &>/dev/null || error "Terraform is required."
command -v func     &>/dev/null || error "Azure Functions Core Tools (func) are required."

az account show &>/dev/null || error "Not logged in to Azure. Run: az login"

ENV="${1:-dev}"
info "Deploying environment: $ENV"

# ── Terraform ────────────────────────────────────────────────────────────────
TF_DIR="$ROOT_DIR/infra/terraform"

info "Initializing Terraform..."
terraform -chdir="$TF_DIR" init -input=false

info "Selecting Terraform workspace: $ENV"
terraform -chdir="$TF_DIR" workspace select "$ENV" 2>/dev/null \
    || terraform -chdir="$TF_DIR" workspace new "$ENV"

info "Running Terraform plan..."
terraform -chdir="$TF_DIR" plan \
    -var="environment=$ENV" \
    -out=tfplan

read -rp "Apply Terraform plan? [y/N] " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    info "Applying Terraform..."
    terraform -chdir="$TF_DIR" apply tfplan
else
    info "Terraform apply cancelled."
    exit 0
fi

# ── Capture Terraform outputs ────────────────────────────────────────────────
FUNC_APP_NAME=$(terraform -chdir="$TF_DIR" output -raw function_app_name)
RG_NAME=$(terraform -chdir="$TF_DIR" output -raw resource_group_name)

# ── Deploy Azure Functions ───────────────────────────────────────────────────
FUNC_DIR="$ROOT_DIR/functions"

info "Publishing Azure Functions to $FUNC_APP_NAME..."
cd "$FUNC_DIR"
func azure functionapp publish "$FUNC_APP_NAME" --python

info "Deployment complete!"
echo ""
echo "  Function App:  $FUNC_APP_NAME"
echo "  Resource Group: $RG_NAME"
echo "  Health check:   https://$FUNC_APP_NAME.azurewebsites.net/api/health"
