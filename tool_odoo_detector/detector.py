"""Best-effort public Odoo detection for the Instant Detector tool.

Security model (same family as the discovery probe):
- Every target (including every redirect hop) passes the shared validate_target()
  gate: https-only, private/reserved IP ranges rejected (SSRF).
- At most THREE small requests per check: homepage GET, an optional
  /web/login GET when the homepage is inconclusive, and an optional
  /web/webclient/version_info POST when Odoo was detected. No crawling,
  no port scanning, no login attempts, no private endpoints.
- Short timeouts, hard response-size cap, response bodies are scanned in
  memory and never stored.

The verdict is always phrased as "appears to" — public signals are
heuristics, not proof.
"""
import json
import logging
import re
import urllib.request

from tools_core.connectors import ConnectorError
from tools_core.connectors.xmlrpc_connector import validate_target

logger = logging.getLogger('bidatia.tools')

FETCH_TIMEOUT = 6
MAX_RESPONSE_BYTES = 262144  # 256 KB is plenty to see <head> + asset tags
USER_AGENT = 'BidERP-OdooDetector/1.0 (+https://bidatia.xyz/tools/odoo-detector/)'

# Confidence thresholds over the summed signal weights.
HIGH_SCORE = 7
MEDIUM_SCORE = 4
WEAK_SCORE = 2


class DetectorError(Exception):
    """Invalid or blocked input URL — message is safe to show the visitor."""


# (evidence code, weight, pattern) — scanned against the homepage HTML.
_HTML_SIGNALS = (
    ('generator_meta', 5,
     re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\'][^"\']*odoo', re.I)),
    ('asset_bundle', 4, re.compile(r'web\.assets_(frontend|common)', re.I)),
    ('web_assets_path', 3, re.compile(r'["\'/]web/assets/', re.I)),
    ('odoo_js', 3,
     re.compile(r'odoo\.define\s*\(|var\s+odoo\s*=|window\.odoo|odoo\.__session_info__', re.I)),
    ('website_markers', 3, re.compile(r'data-oe-|oe_structure', re.I)),
)

# Markers that make a fetched /web/login page convincingly Odoo's.
_LOGIN_MARKERS = re.compile(r'oe_login_form|web\.assets_|/web/login', re.I)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validates every redirect hop so a public URL cannot bounce the
    fetcher into a private address (SSRF via redirect)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            validate_target(newurl)
        except ConnectorError:
            return None  # urllib turns this into an HTTPError → fetch fails
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirectHandler())


def detect(url):
    """Run the public-signal check. Returns a dict:

    detected   'yes' | 'no' | 'unknown'
    confidence 'high' | 'medium' | 'low'
    version    e.g. '17.0' or '' when not safely determinable
    hosting    'odoo_online' | 'odoo_sh' | 'self_hosted' | 'unknown'
    evidence   list of evidence codes (translated to labels by the view)
    domain     normalized hostname that was checked

    Raises DetectorError for invalid/blocked input URLs.
    """
    try:
        base_url, _scheme, hostname = validate_target(url)
    except ConnectorError as exc:
        raise DetectorError(str(exc)) from exc

    evidence = []
    score = 0
    hosting = 'unknown'

    host = hostname.lower()
    if host == 'odoo.com' or host.endswith('.odoo.com'):
        evidence.append('odoo_online_host')
        score += 5
        hosting = 'odoo_online'
    elif host.endswith('.odoo.sh'):
        evidence.append('odoo_sh_host')
        score += 5
        hosting = 'odoo_sh'

    html, headers = _fetch(base_url + '/')
    fetched = html is not None
    if fetched:
        score += _scan_html(html, evidence)
        score += _scan_headers(headers, evidence)

    # Second (and last) page only when the homepage was inconclusive.
    if fetched and score < MEDIUM_SCORE:
        login_html, _headers = _fetch(base_url + '/web/login')
        if login_html and _LOGIN_MARKERS.search(login_html):
            evidence.append('login_page')
            score += 4

    detected, confidence = _classify(score, fetched)

    version = ''
    if detected == 'yes':
        version = _extract_generator_version(html or '') or _version_probe(base_url)
        if version:
            evidence.append('version_reported')
        if hosting == 'unknown':
            hosting = 'self_hosted'

    return {
        'detected': detected,
        'confidence': confidence,
        'version': version,
        'hosting': hosting,
        'evidence': evidence,
        'domain': host,
    }


def _fetch(url):
    """GET one public page. Returns (text, headers) or (None, None) — a
    fetch failure is a normal outcome, never an exception."""
    request = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            body = response.read(MAX_RESPONSE_BYTES)
            headers = response.headers
    except Exception as exc:  # noqa: BLE001 — unreachable sites are expected
        logger.info('odoo detector: fetch failed for %s (%s)', url, type(exc).__name__)
        return None, None
    return body.decode('utf-8', errors='replace'), headers


def _scan_html(html, evidence):
    score = 0
    for code, weight, pattern in _HTML_SIGNALS:
        if pattern.search(html):
            evidence.append(code)
            score += weight
    return score


def _scan_headers(headers, evidence):
    score = 0
    cookies = ' '.join(headers.get_all('Set-Cookie') or [])
    if 'frontend_lang' in cookies:
        evidence.append('frontend_cookie')
        score += 2
    if 'session_id' in cookies:
        evidence.append('session_cookie')
        score += 1
    return score


def _classify(score, fetched):
    if not fetched:
        return 'unknown', 'low'
    if score >= HIGH_SCORE:
        return 'yes', 'high'
    if score >= MEDIUM_SCORE:
        return 'yes', 'medium'
    if score >= WEAK_SCORE:
        return 'unknown', 'low'
    return 'no', 'medium'


def _extract_generator_version(html):
    """Some Odoo sites expose the version in the generator meta tag."""
    match = re.search(
        r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']odoo\s*([\d.]+)', html, re.I)
    return _clean_version(match.group(1)) if match else ''


def _version_probe(base_url):
    """Ask the standard public version endpoint; '' on any failure. Same
    unauthenticated JSON-RPC family as /web/database/list discovery."""
    body = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': {}}).encode()
    request = urllib.request.Request(
        base_url + '/web/webclient/version_info',
        data=body,
        headers={'Content-Type': 'application/json', 'User-Agent': USER_AGENT},
    )
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            data = json.loads(response.read(65536))
    except Exception:  # noqa: BLE001 — endpoint is often disabled; that's fine
        return ''
    result = data.get('result') if isinstance(data, dict) else None
    if not isinstance(result, dict):
        return ''
    return _clean_version(str(result.get('server_version') or ''))


def _clean_version(raw):
    match = re.match(r'(\d+\.\d+)', (raw or '').strip())
    return match.group(1) if match else ''
