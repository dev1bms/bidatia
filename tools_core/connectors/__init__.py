from .base import BaseConnector, ConnectionInfo, ConnectorError
from .xmlrpc_connector import OdooXmlRpcConnector

__all__ = ['BaseConnector', 'ConnectionInfo', 'ConnectorError', 'OdooXmlRpcConnector']
