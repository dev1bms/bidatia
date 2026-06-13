"""Connector interface shared by all data sources (XML-RPC now; postgres /
JSON-upload connectors plug in here in later phases)."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class ConnectorError(Exception):
    """User-presentable connection error.

    The message is shown directly to the visitor and stored on ToolRun, so it
    must NEVER contain credentials, full URLs or internal paths.
    """


@dataclass
class ConnectionInfo:
    server_version: str  # e.g. "17.0"
    edition: str         # "enterprise" | "community" | "" (unknown)
    user_name: str
    db_name: str


class BaseConnector(ABC):
    @abstractmethod
    def test_connection(self) -> ConnectionInfo:
        """Authenticate and return server metadata. Fast — safe to call from a view."""

    @abstractmethod
    def search_read(self, model, domain, fields, limit=None, order=None) -> list:
        ...

    @abstractmethod
    def search_count(self, model, domain) -> int:
        ...

    @abstractmethod
    def read_group(self, model, domain, fields, groupby) -> list:
        ...

    @abstractmethod
    def fields_get(self, model, attributes=None) -> dict:
        ...
