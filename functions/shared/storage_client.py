"""
Azure Table Storage client.

Provides a thin wrapper around the azure-data-tables SDK for
persisting and querying cost records, waste findings, recommendations,
and alerts in Azure Table Storage.
"""

from __future__ import annotations

import logging
from typing import Any

from azure.core.exceptions import AzureError, HttpResponseError, ResourceExistsError
from azure.data.tables import TableServiceClient, TableClient

from shared.config import settings

logger = logging.getLogger(__name__)


class StorageClient:
    """Manages Azure Table Storage operations for the governance system."""

    def __init__(self, connection_string: str | None = None):
        conn = connection_string or settings.STORAGE_CONNECTION_STRING
        self._service = TableServiceClient.from_connection_string(conn)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create tables if they do not exist."""
        for name in (
            settings.COST_TABLE_NAME,
            settings.WASTE_TABLE_NAME,
            settings.RECOMMENDATIONS_TABLE_NAME,
            settings.ALERTS_TABLE_NAME,
        ):
            try:
                self._service.create_table_if_not_exists(name)
            except (AzureError, ResourceExistsError):
                logger.warning("Could not ensure table %s exists", name)

    def _get_table(self, table_name: str) -> TableClient:
        return self._service.get_table_client(table_name)

    # ── Write operations ─────────────────────────────────────────────────

    def upsert_entities(self, table_name: str, entities: list[dict]) -> int:
        """Upsert a batch of entities. Returns count of successful writes."""
        table = self._get_table(table_name)
        count = 0
        for entity in entities:
            try:
                table.upsert_entity(entity, mode="Replace")
                count += 1
            except (AzureError, HttpResponseError):
                logger.warning(
                    "Failed to upsert entity PK=%s RK=%s",
                    entity.get("PartitionKey", "?"),
                    entity.get("RowKey", "?"),
                )
        logger.info("Upserted %d/%d entities into %s", count, len(entities), table_name)
        return count

    def insert_entity(self, table_name: str, entity: dict) -> bool:
        """Insert a single entity (upsert). Returns success flag."""
        try:
            table = self._get_table(table_name)
            table.upsert_entity(entity, mode="Replace")
            return True
        except (AzureError, HttpResponseError):
            logger.exception("Failed to insert entity into %s", table_name)
            return False

    # ── Read operations ──────────────────────────────────────────────────

    def query_entities(
        self,
        table_name: str,
        filter_expr: str | None = None,
        top: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query entities with optional OData filter and top-N limit."""
        table = self._get_table(table_name)
        kwargs: dict[str, Any] = {}
        if filter_expr:
            kwargs["query_filter"] = filter_expr
        if top:
            kwargs["results_per_page"] = top

        entities: list[dict[str, Any]] = []
        try:
            for entity in table.query_entities(**kwargs):
                entities.append(dict(entity))
        except (AzureError, HttpResponseError):
            logger.exception("Failed to query %s", table_name)
        return entities

    def get_all(self, table_name: str) -> list[dict[str, Any]]:
        """Return all entities in the table."""
        return self.query_entities(table_name)

    def delete_all(self, table_name: str) -> None:
        """Delete all entities in the table (for cleanup/testing)."""
        table = self._get_table(table_name)
        try:
            for entity in table.query_entities(""):
                table.delete_entity(
                    partition_key=entity["PartitionKey"],
                    row_key=entity["RowKey"],
                )
        except (AzureError, HttpResponseError):
            logger.exception("Failed to clear table %s", table_name)
