"""Database-name discovery for tool landing forms.

Strategy, in order:
1. Ask the server itself: POST /web/database/list (Odoo's standard JSON-RPC
   endpoint). Works whenever the instance allows database listing.
2. Hosting heuristic: for https://mycompany.odoo.com the database is almost
   always the subdomain.

Goes through the SAME validate_target() gate as the connector, so the SSRF
and https-only rules apply. Strictly read-only and best-effort: any probe
failure simply yields no suggestion.
"""
import json
import logging
import urllib.request

from .xmlrpc_connector import validate_target

logger = logging.getLogger('bidatia.tools')

LIST_TIMEOUT = 8
MAX_RESPONSE_BYTES = 65536
MAX_DATABASES = 50

# Hosted-Odoo parents where the subdomain conventionally names the database.
_HOSTED_PARENTS = ('.odoo.com', '.odoo.sh')


def detect_databases(url):
    """Returns {'databases': [...], 'suggestion': str, 'source': str}.

    source: 'server' (authoritative list), 'heuristic' (subdomain guess)
    or '' (nothing found). Raises ConnectorError for invalid/SSRF URLs.
    """
    base_url, _scheme, hostname = validate_target(url)

    databases = _database_list(base_url)
    if databases:
        return {
            'databases': databases,
            'suggestion': databases[0] if len(databases) == 1 else '',
            'source': 'server',
        }

    suggestion = _subdomain_suggestion(hostname)
    if suggestion:
        return {'databases': [], 'suggestion': suggestion, 'source': 'heuristic'}
    return {'databases': [], 'suggestion': '', 'source': ''}


def _database_list(base_url):
    body = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {}}).encode()
    request = urllib.request.Request(
        base_url + '/web/database/list',
        data=body,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=LIST_TIMEOUT) as response:
            data = json.loads(response.read(MAX_RESPONSE_BYTES))
    except Exception as exc:  # noqa: BLE001 — listing is commonly disabled
        logger.info('db discovery: list endpoint unavailable (%s)', type(exc).__name__)
        return None

    result = data.get('result') if isinstance(data, dict) else None
    if not isinstance(result, list):
        return None
    names = [name for name in result if isinstance(name, str) and name][:MAX_DATABASES]
    return names or None


def _subdomain_suggestion(hostname):
    host = (hostname or '').lower()
    for parent in _HOSTED_PARENTS:
        if host.endswith(parent):
            subdomain = host[:-len(parent)]
            # one clean label only — multi-level subdomains aren't db names
            if subdomain and '.' not in subdomain and subdomain != 'www':
                return subdomain
    return ''
