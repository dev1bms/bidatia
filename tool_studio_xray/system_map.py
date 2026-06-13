"""Server-side "System Map" for the X-Ray report — pure Python, no deps.

Turns the stored result_json into a deterministic radial SVG layout:
models are nodes (size = how much lives in them), custom-field density is
a halo, automations are warm threads back to the Odoo core, risky custom
models glow warm, abandoned ones fade out. The template only paints the
numbers computed here — no logic in the SVG.

Everything is optional-data tolerant: old reports without usage data still
get a map from the model breakdown alone, and build_map() returns None when
there is not enough to draw something meaningful (the report section hides).
"""
import math

from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from .analyzer import CORE_MODELS

VIEW_W = 800
VIEW_H = 620
CX = VIEW_W / 2
CY = VIEW_H / 2 - 6

CENTER_R = 38
RING_RADII = {'core': 112, 'standard': 178, 'custom': 248}
RING_JITTER = 12          # deterministic radius wobble so rings feel organic
MIN_NODE_R = 12
MAX_NODE_R = 28
MAX_NODES = 14
MIN_NODES_FOR_MAP = 3
LABEL_MAX_CHARS = 22
MAX_THREADS_PER_NODE = 4  # automations fan out as parallel threads, capped

FILL = {
    'core': '#f59e0b',        # amber — standard models carrying custom fields
    'standard': '#2778ea',    # brand blue — other standard models
    'custom': '#f43f5e',      # rose — Studio/custom models
    'custom_critical': '#be123c',  # deep rose — business-critical custom models
    'dead': '#94a3b8',        # slate — empty/abandoned custom models
}
THREAD_COLOR = '#f97316'      # automations
SPOKE_COLOR = '#cbd5e1'


def build_map(result_json):
    """Returns the drawing dict for the SVG template, or None when the
    report does not contain enough model data to draw a useful map."""
    result = result_json or {}
    analysis = result.get('analysis') or {}
    breakdown = analysis.get('model_breakdown') or []
    usage_rows = (result.get('usage') or {}).get('rows') or []
    meta = result.get('meta') or {}

    nodes = _merge_nodes(breakdown, usage_rows)
    if len(nodes) < MIN_NODES_FOR_MAP:
        return None
    nodes = nodes[:MAX_NODES]

    _assign_geometry(nodes)

    spokes, threads = [], []
    for i, node in enumerate(nodes):
        spokes.append({'x2': node['x'], 'y2': node['y']})
        threads.extend(_node_threads(node, flip=bool(i % 2)))

    version = str(meta.get('server_version') or '').strip()
    return {
        'view_w': VIEW_W, 'view_h': VIEW_H, 'cx': CX, 'cy': CY,
        'center_r': CENTER_R,
        'center_halo_r': CENTER_R + 7,
        'center_label': ('Odoo %s' % version) if version else 'Odoo',
        # Captions sit on each ring at different angles on the left side so
        # they never read as one merged phrase.
        'rings': [
            {'r': radius, 'label': label,
             'label_x': round(CX + radius * math.cos(math.radians(angle)), 1),
             'label_y': round(CY + radius * math.sin(math.radians(angle)) - 7, 1)}
            for radius, label, angle in (
                (RING_RADII['core'], _('Core'), 180),
                (RING_RADII['standard'], _('Standard'), 152),
                (RING_RADII['custom'], _('Custom'), 196),
            )
        ],
        'spoke_color': SPOKE_COLOR,
        'thread_color': THREAD_COLOR,
        'spokes': spokes,
        'threads': threads,
        'nodes': nodes,
        'custom_count': sum(1 for n in nodes if n['kind'] == 'custom'),
        'automation_total': sum(n['automations'] for n in nodes),
    }


def _node_threads(node, flip):
    """One curved thread per automation (capped), fanned with different
    bends — a tidy cable bundle instead of one ambiguous line."""
    count = min(node['automations'], MAX_THREADS_PER_NODE)
    if not count:
        return []
    if count == 1:
        bends = [-26 if flip else 26]
    else:
        spread = 64
        bends = [round(-spread / 2 + spread * i / (count - 1)) for i in range(count)]
        # A dead-straight middle thread would hide under the spoke.
        bends = [b if abs(b) >= 8 else (8 if flip else -8) for b in bends]
    return [{'d': _thread_path(node['x'], node['y'], bend=b), 'width': 2.0}
            for b in bends]


def _merge_nodes(breakdown, usage_rows):
    """Union of the customization breakdown and the custom-model usage rows."""
    by_model = {}
    for row in breakdown:
        model = (row.get('model') or '').strip()
        if not model:
            continue
        by_model[model] = {
            'model': model,
            'fields': int(row.get('fields') or 0),
            'views': int(row.get('views') or 0),
            'automations': int(row.get('automations') or 0),
            'load': int(row.get('total') or 0),
            'records': None,
            'tier': '',
        }
    for row in usage_rows:
        model = (row.get('model') or '').strip()
        if not model:
            continue
        node = by_model.setdefault(model, {
            'model': model, 'fields': 0, 'views': 0, 'automations': 0,
            'load': 0, 'records': None, 'tier': '',
        })
        node['records'] = int(row.get('records') or 0)
        node['tier'] = row.get('tier') or ''

    nodes = list(by_model.values())
    for node in nodes:
        node['kind'] = _kind(node['model'])
    # Heaviest first — they get the most prominent angular slots.
    nodes.sort(key=lambda n: (-(n['records'] or 0), -n['load'], n['model']))
    return nodes


def _kind(model):
    if model.startswith('x_') or '.x_' in model:
        return 'custom'
    return 'core' if model in CORE_MODELS else 'standard'


def _assign_geometry(nodes):
    rec_max = max((n['records'] or 0 for n in nodes), default=0)
    load_max = max((n['load'] for n in nodes), default=0)

    ring_members = {'core': [], 'standard': [], 'custom': []}
    for node in nodes:
        ring_members[node['kind']].append(node)

    ring_offsets = {'core': -90.0, 'standard': -72.0, 'custom': -54.0}
    for kind, members in ring_members.items():
        step = 360.0 / len(members) if members else 0
        for i, node in enumerate(members):
            radius = RING_RADII[kind] + (i % 3 - 1) * RING_JITTER
            angle = math.radians(ring_offsets[kind] + i * step)
            node['x'] = round(CX + radius * math.cos(angle), 1)
            node['y'] = round(CY + radius * math.sin(angle), 1)

    for node in nodes:
        rec_norm = (math.sqrt(node['records']) / math.sqrt(rec_max)
                    if rec_max and node['records'] else 0.0)
        load_norm = (math.sqrt(node['load']) / math.sqrt(load_max)
                     if load_max and node['load'] else 0.0)
        norm = max(rec_norm, load_norm)
        node['r'] = round(MIN_NODE_R + (MAX_NODE_R - MIN_NODE_R) * norm, 1)

        is_dead = node['kind'] == 'custom' and node['records'] == 0
        if is_dead:
            node['fill'], node['opacity'] = FILL['dead'], 0.45
        elif node['kind'] == 'custom':
            critical = node['tier'] == 'critical'
            node['fill'] = FILL['custom_critical'] if critical else FILL['custom']
            node['opacity'] = 1.0
        else:
            node['fill'], node['opacity'] = FILL[node['kind']], 1.0

        # Custom-field density halo.
        if node['fields']:
            node['halo_r'] = round(node['r'] + 5 + min(node['fields'], 24) * 0.45, 1)
        else:
            node['halo_r'] = None

        node['label'] = _short(node['model'])
        node['sub'] = _node_stat(node)
        node['label_y'] = round(node['y'] + node['r'] + 15, 1)
        node['sub_y'] = round(node['y'] + node['r'] + 29, 1)


def _node_stat(node):
    """One short stat line under the name — the single most telling number
    for this node. Translated at build time (build_map runs per request)."""
    if node['records'] is not None and node['records'] > 0:
        return (ngettext('%(n)s record', '%(n)s records', node['records'])
                % {'n': _human(node['records'])})
    if node['kind'] == 'custom' and node['records'] == 0:
        return _('no records')
    if node['fields']:
        return (ngettext('%(n)s custom field', '%(n)s custom fields',
                         node['fields']) % {'n': node['fields']})
    if node['automations']:
        return (ngettext('%(n)s automation', '%(n)s automations',
                         node['automations']) % {'n': node['automations']})
    if node['views']:
        return (ngettext('%(n)s custom view', '%(n)s custom views',
                         node['views']) % {'n': node['views']})
    return ''


def _thread_path(x, y, bend):
    """Quadratic bezier from the core to (x, y), bowed sideways for the
    woven-threads look."""
    mx, my = (CX + x) / 2, (CY + y) / 2
    length = math.hypot(x - CX, y - CY) or 1.0
    # Unit perpendicular to the spoke direction.
    px, py = -(y - CY) / length, (x - CX) / length
    qx, qy = mx + px * bend, my + py * bend
    return 'M%.1f %.1f Q%.1f %.1f %.1f %.1f' % (CX, CY, qx, qy, x, y)


def _short(model):
    return model if len(model) <= LABEL_MAX_CHARS else model[:LABEL_MAX_CHARS - 1] + '…'


def _human(n):
    n = n or 0
    if n >= 1000:
        text = '%.1f' % (n / 1000.0)
        return (text[:-2] if text.endswith('.0') else text) + 'k'
    return str(n)
