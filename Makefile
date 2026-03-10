.PHONY: help install test lint clean docker-up docker-down seed

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	python -m pip install --upgrade pip
	pip install -r requirements.txt

test: ## Run test suite with coverage
	python -m pytest tests/ -v --tb=short --cov=functions --cov-report=term-missing

lint: ## Run linter
	python -m ruff check functions/ tests/

clean: ## Clean caches and artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name *.egg-info -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage

docker-up: ## Start local development stack (Azurite + Grafana)
	docker-compose up -d

docker-down: ## Stop local development stack
	docker-compose down

seed: ## Seed sample cost data for local testing
	python scripts/seed_data.py

deploy: ## Deploy to Azure using Terraform
	cd infra/terraform && terraform init && terraform plan -out=tfplan && terraform apply tfplan

validate: ## Validate Terraform configuration
	cd infra/terraform && terraform init -backend=false && terraform validate
