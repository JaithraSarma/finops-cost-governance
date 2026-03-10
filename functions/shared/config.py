"""
Centralised configuration — reads from environment variables with sensible defaults.
"""

import os


class Settings:
    """Application settings loaded from environment variables."""

    # Azure identity
    SUBSCRIPTION_ID: str = os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    TENANT_ID: str = os.environ.get("AZURE_TENANT_ID", "")

    # Storage
    STORAGE_CONNECTION_STRING: str = os.environ.get(
        "STORAGE_CONNECTION_STRING",
        "UseDevelopmentStorage=true",
    )
    COST_TABLE_NAME: str = os.environ.get("COST_TABLE_NAME", "CostRecords")
    WASTE_TABLE_NAME: str = os.environ.get("WASTE_TABLE_NAME", "WasteResources")
    RECOMMENDATIONS_TABLE_NAME: str = os.environ.get("RECOMMENDATIONS_TABLE_NAME", "Recommendations")
    ALERTS_TABLE_NAME: str = os.environ.get("ALERTS_TABLE_NAME", "Alerts")

    # Logic App webhooks
    SLACK_WEBHOOK_URL: str = os.environ.get("LOGIC_APP_SLACK_WEBHOOK_URL", "")
    TEAMS_WEBHOOK_URL: str = os.environ.get("LOGIC_APP_TEAMS_WEBHOOK_URL", "")

    # Thresholds
    DAILY_BUDGET_LIMIT: float = float(os.environ.get("DAILY_BUDGET_LIMIT", "500"))
    MONTHLY_BUDGET_LIMIT: float = float(os.environ.get("MONTHLY_BUDGET_LIMIT", "15000"))
    COST_ANOMALY_THRESHOLD_PERCENT: float = float(
        os.environ.get("COST_ANOMALY_THRESHOLD_PERCENT", "20")
    )
    WASTE_ALERT_MIN_SAVINGS: float = float(
        os.environ.get("WASTE_ALERT_MIN_SAVINGS", "50")
    )

    # Lookback windows (days)
    COST_LOOKBACK_DAYS: int = int(os.environ.get("COST_LOOKBACK_DAYS", "30"))


settings = Settings()
