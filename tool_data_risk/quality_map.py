"""Data Quality Map — a radar (spider) chart of the 8 category scores.

Pure Python like the X-Ray System Map: every coordinate/color is computed
here, the template only paints attributes inside {% localize off %}.
Deterministic, no dependencies, no raw data — category codes and scores
only. Returns None when fewer than 3 categories were scored (section hides).
"""
import math

VIEW_W = 560
VIEW_H = 520
CX = VIEW_W / 2
CY = VIEW_H / 2 + 6
R_MAX = 170
R_MIN = 26          # ring around the center score chip
LABEL_R = R_MAX + 26
RINGS = (25, 50, 75, 100)
MIN_AXES = 3

SEVERITY_COLORS = {
    'ok': '#10b981',
    'info': '#2778ea',
    'warning': '#f59e0b',
    'critical': '#be123c',
}

LEVEL_COLORS = {
    'low': '#10b981',
    'moderate': '#f59e0b',
    'high': '#f97316',
    'critical': '#be123c',
}


def build_quality_map(risk, category_labels):
    """`category_labels` maps code → translated short label (built per
    request in the view, so the SVG text follows the page language)."""
    scored = [c for c in (risk or {}).get('categories') or []
              if c.get('score') is not None]
    if len(scored) < MIN_AXES:
        return None

    count = len(scored)
    axes, points = [], []
    for i, category in enumerate(scored):
        angle = math.radians(-90 + i * 360.0 / count)
        cos, sin = math.cos(angle), math.sin(angle)
        score = category['score']
        radius = R_MIN + (R_MAX - R_MIN) * score / 100.0
        px, py = CX + radius * cos, CY + radius * sin
        points.append('%.1f,%.1f' % (px, py))
        label_x = CX + LABEL_R * cos
        anchor = ('middle' if abs(cos) < 0.35
                  else 'start' if cos > 0 else 'end')
        axes.append({
            'x2': round(CX + R_MAX * cos, 1),
            'y2': round(CY + R_MAX * sin, 1),
            'px': round(px, 1), 'py': round(py, 1),
            'dot_color': SEVERITY_COLORS.get(category.get('severity'), '#64748b'),
            'label': str(category_labels.get(category['code'], category['code'])),
            'score': score,
            'label_x': round(label_x, 1),
            'label_y': round(CY + LABEL_R * sin, 1),
            'value_y': round(CY + LABEL_R * sin + 13, 1),
            'anchor': anchor,
        })

    level = (risk or {}).get('level') or 'low'
    return {
        'view_w': VIEW_W, 'view_h': VIEW_H, 'cx': CX, 'cy': CY,
        'rings': [{'r': round(R_MIN + (R_MAX - R_MIN) * ring / 100.0, 1)}
                  for ring in RINGS],
        'axes': axes,
        'polygon': ' '.join(points),
        'score': (risk or {}).get('score') or 0,
        'score_color': LEVEL_COLORS.get(level, '#64748b'),
        'center_r': R_MIN - 4,
    }
