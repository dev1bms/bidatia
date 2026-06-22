"""Read-only Odoo XML-RPC connector.

Security model (Phase 1 plan §5):
- HTTPS-only target URLs; http allowed only for private hosts while DEBUG.
- SSRF protection: hostnames are resolved up front and private/reserved
  ranges rejected, so the tools cannot probe the BidERP internal network.
- Hard whitelist of read-only ORM methods — there is no generic execute().
- Credentials live only in this object's memory for the duration of a run;
  they are never logged, persisted or echoed back in error messages.
- Politeness: per-call socket timeout, a small sleep between data calls,
  an enforced record limit per call and a global call budget per run.
"""
import ipaddress
import logging
import socket
import ssl
import time
from urllib.parse import urlsplit
from xmlrpc import client as xmlrpc_client

from django.conf import settings

from .base import BaseConnector, ConnectionInfo, ConnectorError

logger = logging.getLogger('bidatia.tools')

ALLOWED_METHODS = ('search_read', 'search_count', 'read_group', 'fields_get')
HARD_RECORD_LIMIT = 2000
MAX_CALLS_PER_RUN = 200
CALL_SLEEP_SECONDS = 0.06
DEFAULT_TIMEOUT = 30

# Private / reserved ranges we refuse to connect to (plan §5.2), plus the
# Tailscale CGNAT range which counts as "private" for the DEBUG http carve-out.
_PRIVATE_NETS = [ipaddress.ip_network(net) for net in (
    '127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
    '169.254.0.0/16', '100.64.0.0/10',
    '::1/128', 'fc00::/7', 'fe80::/10',
)]

_ERR_BAD_URL = 'Enter a valid Odoo URL, for example https://mycompany.odoo.com'
_ERR_AUTH = 'Authentication failed — check the database name, login and API key.'
_ERR_DB = 'Database name not found or access denied.'


class _TimeoutTransport(xmlrpc_client.Transport):
    def __init__(self, timeout):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class _TimeoutSafeTransport(xmlrpc_client.SafeTransport):
    def __init__(self, timeout):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


def _is_private(ip_text):
    addr = ipaddress.ip_address(ip_text)
    return any(addr in net for net in _PRIVATE_NETS)


def validate_target(url):
    """Shared URL/SSRF gate: normalize + enforce scheme and private-range
    rules. Returns (base_url, scheme, hostname); raises ConnectorError.
    Used by the connector AND by lighter probes (database discovery)."""
    base_url, scheme, hostname = OdooXmlRpcConnector._normalize_url(url)
    _enforce_target_rules(scheme, hostname)
    return base_url, scheme, hostname


def _enforce_target_rules(scheme, hostname):
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ConnectorError('Could not resolve the server address — check the URL.')
    ips = {info[4][0] for info in infos}
    has_private = any(_is_private(ip) for ip in ips)

    if scheme == 'http':
        # http is a local-development convenience only.
        if not (settings.DEBUG and has_private):
            raise ConnectorError('Only https:// Odoo URLs are supported.')
    elif has_private and not settings.DEBUG:
        raise ConnectorError('This address is not reachable from our network.')


class OdooXmlRpcConnector(BaseConnector):
    def __init__(self, url, db, login, api_key, timeout=DEFAULT_TIMEOUT):
        self._base_url, self._scheme, hostname = self._normalize_url(url)
        self._check_target(hostname)
        self._db = (db or '').strip()
        self._login = (login or '').strip()
        self._api_key = api_key or ''
        if not (self._db and self._login and self._api_key):
            raise ConnectorError('Database, login and API key are all required.')
        self._timeout = timeout
        self._uid = None
        self._call_count = 0

    # -- URL validation & SSRF ------------------------------------------------

    @staticmethod
    def _normalize_url(raw):
        raw = (raw or '').strip()
        if not raw:
            raise ConnectorError(_ERR_BAD_URL)
        if '://' not in raw:
            raw = 'https://' + raw
        parts = urlsplit(raw)
        scheme = parts.scheme.lower()
        if scheme not in ('http', 'https') or not parts.hostname:
            raise ConnectorError(_ERR_BAD_URL)
        return f'{scheme}://{parts.netloc}', scheme, parts.hostname

    def _check_target(self, hostname):
        """Resolve the hostname and enforce the scheme/SSRF rules.

        Note: this is a resolve-time check; DNS-rebinding between check and
        connect is out of scope for Phase 1 (documented in the plan).
        """
        _enforce_target_rules(self._scheme, hostname)

    # -- proxies & error handling ---------------------------------------------

    def _proxy(self, path):
        transport_cls = _TimeoutSafeTransport if self._scheme == 'https' else _TimeoutTransport
        return xmlrpc_client.ServerProxy(
            f'{self._base_url}/xmlrpc/2/{path}',
            transport=transport_cls(self._timeout),
            allow_none=True,
        )

    def _sanitize(self, text):
        """Strip anything secret or internal from error text before it can be
        shown, stored or logged."""
        text = str(text)
        for secret in (self._api_key, self._login):
            if secret:
                text = text.replace(secret, '***')
        host = urlsplit(self._base_url).netloc
        if host:
            text = text.replace(host, '<server>')
        return text

    def _friendly_error(self, exc):
        # Log the REAL server error (with credentials/host masked) so operators
        # can diagnose connection failures — the visitor only ever sees the
        # friendly message returned below.
        if isinstance(exc, xmlrpc_client.Fault):
            # Odoo returns its full server-side traceback as the fault string;
            # keep the tail (where the actual exception line lives) so the log
            # stays useful without flooding.
            fault_text = self._sanitize(exc.faultString or '').rstrip()
            if len(fault_text) > 700:
                fault_text = '…' + fault_text[-700:]
            logger.warning(
                'xmlrpc connector: Odoo Fault [code=%s] db=%r host=%s — %s',
                getattr(exc, 'faultCode', '?'),
                self._db, urlsplit(self._base_url).netloc,
                fault_text,
            )
        else:
            logger.warning(
                'xmlrpc connector: %s db=%r host=%s — %s',
                type(exc).__name__, self._db, urlsplit(self._base_url).netloc,
                self._sanitize(str(exc)),
            )

        if isinstance(exc, xmlrpc_client.Fault):
            fault = self._sanitize(exc.faultString or '')
            lowered = fault.lower()
            if 'database' in lowered:
                return ConnectorError(_ERR_DB)
            if 'access denied' in lowered or 'accessdenied' in lowered or 'access error' in lowered:
                return ConnectorError(_ERR_AUTH)
            return ConnectorError('The Odoo server returned an error while processing the request.')
        if isinstance(exc, xmlrpc_client.ProtocolError):
            return ConnectorError(
                f'The server responded with HTTP {exc.errcode} — is this the correct Odoo URL?'
            )
        if isinstance(exc, xmlrpc_client.ResponseError) or isinstance(exc, xmlrpc_client.Error):
            return ConnectorError('The server did not return a valid XML-RPC response — is this the correct Odoo URL?')
        if isinstance(exc, ssl.SSLError):
            return ConnectorError('Could not establish a secure (TLS) connection to the server.')
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return ConnectorError(f'The server did not respond within {self._timeout} seconds.')
        if isinstance(exc, OSError):
            return ConnectorError('Could not reach the server — check the URL and try again.')
        return ConnectorError('Unexpected error while talking to the Odoo server.')

    def _guarded(self, fn):
        try:
            return fn()
        except ConnectorError:
            raise
        except Exception as exc:  # noqa: BLE001 — mapped to a sanitized, friendly error
            raise self._friendly_error(exc) from None

    # -- auth -------------------------------------------------------------------

    def _authenticate(self):
        if self._uid:
            return
        common = self._proxy('common')
        uid = self._guarded(lambda: common.authenticate(self._db, self._login, self._api_key, {}))
        if not uid:
            raise ConnectorError(_ERR_AUTH)
        self._uid = uid

    # -- public API ---------------------------------------------------------------

    def test_connection(self) -> ConnectionInfo:
        common = self._proxy('common')
        version = self._guarded(common.version)
        server_version = str((version or {}).get('server_version', ''))

        self._authenticate()

        users = self.search_read('res.users', [('id', '=', self._uid)], ['name'], limit=1)
        user_name = users[0].get('name', self._login) if users else self._login

        return ConnectionInfo(
            server_version=server_version.replace('+e', ''),
            edition=self._detect_edition(server_version),
            user_name=user_name,
            db_name=self._db,
        )

    def _detect_edition(self, server_version):
        if '+e' in server_version:
            return 'enterprise'
        try:
            count = self.search_count('ir.module.module', [
                ('name', 'in', ['web_enterprise', 'web_studio']),
                ('state', '=', 'installed'),
            ])
        except ConnectorError:
            return ''  # restricted user — edition unknown, report stays usable
        return 'enterprise' if count else 'community'

    def search_read(self, model, domain, fields, limit=None, order=None):
        limit = min(limit or HARD_RECORD_LIMIT, HARD_RECORD_LIMIT)
        kwargs = {'fields': fields, 'limit': limit}
        if order:
            kwargs['order'] = order
        return self._execute(model, 'search_read', [domain], kwargs)

    def search_count(self, model, domain):
        return self._execute(model, 'search_count', [domain])

    def read_group(self, model, domain, fields, groupby):
        return self._execute(model, 'read_group', [domain, fields, groupby], {'lazy': False})

    def fields_get(self, model, attributes=None):
        return self._execute(model, 'fields_get', [], {'attributes': attributes or ['string', 'type']})

    # -- transport ------------------------------------------------------------------

    def _execute(self, model, method, args, kwargs=None):
        if method not in ALLOWED_METHODS:
            raise ConnectorError(f'Method "{method}" is not allowed — this connector is read-only.')
        self._authenticate()

        self._call_count += 1
        if self._call_count > MAX_CALLS_PER_RUN:
            raise ConnectorError(
                'Diagnostic aborted: the run needed too many requests. '
                'Your database may be too large for the online tool.'
            )
        time.sleep(CALL_SLEEP_SECONDS)

        obj = self._proxy('object')
        return self._guarded(
            lambda: obj.execute_kw(self._db, self._uid, self._api_key, model, method, args, kwargs or {})
        )
