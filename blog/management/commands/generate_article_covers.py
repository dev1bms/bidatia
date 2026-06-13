"""Generate original, on-brand cover images for the blog/insights articles.

Why this exists
---------------
Article covers must be ORIGINAL and license-safe (no stock photos, no third-party
brand assets) and visually consistent as one system. Rather than hand-draw six
files, this command renders them deterministically with Pillow: a deep-navy
Bidatia-branded canvas with a per-topic abstract motif (workflow / diagnostics /
modules / migration / integration / data structure).

Design notes
------------
* Output is 1200x630 PNG — the right size for article cards, detail hero images
  AND Open Graph / Twitter social cards (one asset, used everywhere).
* Rendered at 2x and downscaled with LANCZOS, so edges and text are crisp.
* NO localized text is baked in (only the Bidatia wordmark + a neutral tech tag),
  so the same image is correct on the English, Spanish and Arabic pages.
* Files land in ``static/img/insights/<slug>.png`` (committed, collected by
  ``collectstatic``, served by WhiteNoise). A shared ``default.png`` is the
  fallback for any article without its own cover.

Usage
-----
    python manage.py generate_article_covers            # all posts + default
    python manage.py generate_article_covers --slug foo  # one slug

The covers are checked into the repo as static assets; re-run this only when the
article set changes or the visual system is updated.
"""
import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from blog.models import BlogPost

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - Pillow is a project dependency
    Image = None


# ── Canvas ────────────────────────────────────────────────────────────────
W, H = 1200, 630
SS = 2                      # supersample factor (render big, downscale = antialias)
W2, H2 = W * SS, H * SS

# ── Brand palette (matches tailwind.config in base.html) ──────────────────
# Bidatia "RGB" system: slate base, anchor blue, governance green accent.
INK = (15, 23, 42)          # slate-900
NAVY_TOP = (11, 16, 32)
NAVY_BOT = (15, 23, 42)
BRAND = (37, 99, 235)       # brand-600 (#2563eb)
BRAND_LT = (96, 165, 250)   # brand-400 (#60a5fa)
TEAL = (34, 197, 94)        # accent-500 / governance green (#22c55e)
TEAL_LT = (74, 222, 128)    # accent-400 (#4ade80)
WHITE = (255, 255, 255)
SLATE = (148, 163, 184)
# RGB signal trio for the brand accent rule (red → green → blue).
SIG_R = (239, 68, 68)
SIG_G = (34, 197, 94)
SIG_B = (59, 130, 246)


def _f(size):
    """A crisp scalable font at supersampled size (bundled with Pillow)."""
    return ImageFont.load_default(size=int(size * SS))


def _rr(d, box, radius, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=int(radius), fill=fill, outline=outline, width=int(width))


def _quad(p0, p1, p2, steps=48):
    """Points along a quadratic bezier (Pillow has no native curve)."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        out.append((
            mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
            mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1],
        ))
    return out


def _node(d, cx, cy, r, color):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (255,))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 90), width=int(2 * SS))


# ── Background + shared furniture ─────────────────────────────────────────
def _background():
    base = Image.new('RGB', (W2, H2), NAVY_TOP)
    d = ImageDraw.Draw(base)
    for y in range(H2):
        t = y / (H2 - 1)
        d.line([(0, y), (W2, y)], fill=(
            int(NAVY_TOP[0] + (NAVY_BOT[0] - NAVY_TOP[0]) * t),
            int(NAVY_TOP[1] + (NAVY_BOT[1] - NAVY_TOP[1]) * t),
            int(NAVY_TOP[2] + (NAVY_BOT[2] - NAVY_TOP[2]) * t),
        ))
    base = base.convert('RGBA')

    # Soft brand/teal glow, lower-right, for depth.
    glow = Image.new('RGBA', (W2, H2), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(W2 * 0.55), int(H2 * 0.35), int(W2 * 1.15), int(H2 * 1.15)],
               fill=BRAND + (70,))
    gd.ellipse([int(W2 * 0.62), int(H2 * 0.5), int(W2 * 1.05), int(H2 * 1.2)],
               fill=TEAL + (45,))
    glow = glow.filter(ImageFilter.GaussianBlur(int(120 * SS)))
    base.alpha_composite(glow)

    # Fine dot grid (subtle technical texture).
    dots = Image.new('RGBA', (W2, H2), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    gap, r = int(46 * SS), int(1.4 * SS)
    for yy in range(gap, H2, gap):
        for xx in range(gap, W2, gap):
            dd.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(255, 255, 255, 14))
    base.alpha_composite(dots)
    return base


def _rgb_rule(d, x, y, seg, h):
    """A short red → green → blue accent rule (the Bidatia signal)."""
    for i, col in enumerate((SIG_R, SIG_G, SIG_B)):
        d.rectangle([x + i * seg, y, x + (i + 1) * seg, y + h], fill=col + (235,))


def _brand_furniture(base):
    """Bidatia logo mark + wordmark (top-left) and a neutral tech tag (bottom)."""
    d = ImageDraw.Draw(base)
    mx, my = int(64 * SS), int(56 * SS)

    # Logo mark: slate rounded square, "B", and an RGB bar along the bottom.
    s = int(44 * SS)
    _rr(d, [mx, my, mx + s, my + s], radius=12 * SS, fill=INK + (255,),
        outline=(255, 255, 255, 40), width=int(SS))
    bf = _f(26)
    bb = d.textbbox((0, 0), 'B', font=bf)
    d.text((mx + (s - (bb[2] - bb[0])) / 2 - bb[0], my + (s - (bb[3] - bb[1])) / 2 - bb[1]),
           'B', font=bf, fill=WHITE, stroke_width=int(SS), stroke_fill=WHITE)
    _rgb_rule(d, mx + int(7 * SS), my + s - int(9 * SS), int((s - 14 * SS) / 3), int(4 * SS))

    # Wordmark: "Bidatia" white (faux-bold via stroke).
    wf = _f(30)
    tx = mx + s + int(16 * SS)
    ty = my + int(4 * SS)
    d.text((tx, ty), 'Bidatia', font=wf, fill=WHITE, stroke_width=int(SS), stroke_fill=WHITE)
    sf = _f(13)
    d.text((tx + int(2 * SS), ty + int(34 * SS)), 'BUSINESS SYSTEMS', font=sf, fill=SLATE)

    # Neutral tech tag (product/tech terms — language-neutral), bottom-left.
    tag = 'ERP   ·   ODOO   ·   DATA   ·   AI'
    tf = _f(15)
    d.text((int(64 * SS), int(H2 - 70 * SS)), tag, font=tf, fill=SLATE)

    # RGB accent rule above the tag.
    _rgb_rule(d, int(64 * SS), int(H2 - 88 * SS), int(40 * SS), int(4 * SS))


# ── Per-topic motifs (drawn on a transparent overlay, then composited) ────
def _overlay():
    o = Image.new('RGBA', (W2, H2), (0, 0, 0, 0))
    return o, ImageDraw.Draw(o)


def _motif_diagnostics():
    """Health check → scope ring + ECG pulse + nodes."""
    o, d = _overlay()
    cx, cy, R = int(W2 * 0.68), int(H2 * 0.5), int(150 * SS)
    for i, a in enumerate((40, 24, 12)):           # pulse rings
        rr = R + int((i + 1) * 34 * SS)
        d.arc([cx - rr, cy - rr, cx + rr, cy + rr], 300, 60, fill=TEAL + (a + 40,), width=int(4 * SS))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=BRAND_LT + (255,), width=int(5 * SS))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=BRAND + (26,))
    # ECG line across the ring.
    bx = cx - int(R * 0.74)
    pts = [(bx, cy), (bx + int(R * 0.5), cy), (bx + int(R * 0.72), cy - int(R * 0.55)),
           (bx + int(R * 0.95), cy + int(R * 0.5), ), (bx + int(R * 1.12), cy),
           (cx + int(R * 0.78), cy)]
    d.line(pts, fill=TEAL_LT + (255,), width=int(5 * SS), joint='curve')
    _node(d, cx + int(R * 0.78), cy, int(9 * SS), TEAL_LT)
    _node(d, bx, cy, int(9 * SS), BRAND_LT)
    return o


def _motif_modules():
    """Studio vs custom modules → grid of module cards, one promoted."""
    o, d = _overlay()
    cx, cy = int(W2 * 0.66), int(H2 * 0.5)
    cw, ch, gap = int(150 * SS), int(110 * SS), int(28 * SS)
    x0, y0 = cx - cw - gap // 2, cy - ch - gap // 2
    cells = [(0, 0, 'b'), (1, 0, 't'), (0, 1, 't'), (1, 1, 'b')]
    centers = {}
    for ix, iy, kind in cells:
        x = x0 + ix * (cw + gap)
        y = y0 + iy * (ch + gap)
        col = BRAND_LT if kind == 'b' else TEAL
        fill = (BRAND + (40,)) if kind == 'b' else (TEAL + (24,))
        _rr(d, [x, y, x + cw, y + ch], radius=18 * SS, fill=fill, outline=col + (255,), width=int(4 * SS))
        # little "rows" inside each card
        for k in range(2):
            ry = y + int(34 * SS) + k * int(26 * SS)
            d.line([(x + int(20 * SS), ry), (x + cw - int(34 * SS), ry)],
                   fill=(255, 255, 255, 70), width=int(4 * SS))
        centers[(ix, iy)] = (x + cw // 2, y + ch // 2)
    # connectors between the four
    d.line([centers[(0, 0)], centers[(1, 0)]], fill=TEAL + (150,), width=int(3 * SS))
    d.line([centers[(0, 0)], centers[(0, 1)]], fill=TEAL + (150,), width=int(3 * SS))
    d.line([centers[(1, 1)], centers[(1, 0)]], fill=TEAL + (150,), width=int(3 * SS))
    return o


def _motif_migration():
    """Migration → legacy cluster → chevrons → one clean module."""
    o, d = _overlay()
    cy = int(H2 * 0.5)
    # legacy: dim stack
    lx = int(W2 * 0.46)
    for i in range(3):
        off = i * int(14 * SS)
        _rr(d, [lx + off, cy - int(60 * SS) + off, lx + int(120 * SS) + off, cy + int(60 * SS) + off],
            radius=14 * SS, fill=(255, 255, 255, 16), outline=SLATE + (180,), width=int(3 * SS))
    # chevrons
    cxs = int(W2 * 0.64)
    for i in range(3):
        x = cxs + i * int(34 * SS)
        d.line([(x, cy - int(34 * SS)), (x + int(26 * SS), cy), (x, cy + int(34 * SS))],
               fill=TEAL_LT + (255 - i * 40,), width=int(7 * SS), joint='curve')
    # destination module (clean, branded)
    rx = int(W2 * 0.78)
    _rr(d, [rx, cy - int(80 * SS), rx + int(170 * SS), cy + int(80 * SS)],
        radius=22 * SS, fill=BRAND + (55,), outline=BRAND_LT + (255,), width=int(5 * SS))
    d.line([(rx + int(26 * SS), cy - int(26 * SS)), (rx + int(150 * SS) - int(26 * SS), cy - int(26 * SS))],
           fill=(255, 255, 255, 120), width=int(5 * SS))
    d.line([(rx + int(26 * SS), cy + int(6 * SS)), (rx + int(110 * SS), cy + int(6 * SS))],
           fill=(255, 255, 255, 90), width=int(5 * SS))
    _node(d, rx + int(150 * SS), cy + int(40 * SS), int(8 * SS), TEAL_LT)
    return o


def _motif_upgrade():
    """Version upgrade → ascending steps + up arrow."""
    o, d = _overlay()
    baseY = int(H2 * 0.72)
    x = int(W2 * 0.5)
    bw, gap = int(96 * SS), int(26 * SS)
    heights = [int(80 * SS), int(140 * SS), int(210 * SS)]
    cols = [TEAL, BRAND_LT, BRAND_LT]
    fills = [TEAL + (26,), BRAND + (40,), BRAND + (60,)]
    for i, h in enumerate(heights):
        bx = x + i * (bw + gap)
        _rr(d, [bx, baseY - h, bx + bw, baseY], radius=14 * SS, fill=fills[i], outline=cols[i] + (255,), width=int(4 * SS))
    # up arrow above the tallest
    ax = x + 2 * (bw + gap) + bw // 2
    ay = baseY - heights[2] - int(60 * SS)
    d.line([(ax, ay + int(70 * SS)), (ax, ay)], fill=TEAL_LT + (255,), width=int(7 * SS))
    d.line([(ax - int(26 * SS), ay + int(26 * SS)), (ax, ay), (ax + int(26 * SS), ay + int(26 * SS))],
           fill=TEAL_LT + (255,), width=int(7 * SS), joint='curve')
    return o


def _motif_integration():
    """Django + Odoo → two systems linked by a flowing connector."""
    o, d = _overlay()
    cy = int(H2 * 0.5)
    lx, rx = int(W2 * 0.5), int(W2 * 0.86)
    # left node (circle = service)
    _node(d, lx, cy, int(52 * SS), BRAND_LT)
    d.ellipse([lx - int(52 * SS), cy - int(52 * SS), lx + int(52 * SS), cy + int(52 * SS)],
              fill=BRAND + (60,))
    # right node (rounded square = ERP)
    _rr(d, [rx - int(60 * SS), cy - int(60 * SS), rx + int(60 * SS), cy + int(60 * SS)],
        radius=20 * SS, fill=TEAL + (40,), outline=TEAL_LT + (255,), width=int(5 * SS))
    # flowing connector with dots
    curve = _quad((lx + int(54 * SS), cy), ((lx + rx) // 2, cy - int(120 * SS)), (rx - int(62 * SS), cy))
    d.line(curve, fill=TEAL_LT + (220,), width=int(4 * SS), joint='curve')
    for t in (0.25, 0.5, 0.75):
        px, py = curve[int(t * (len(curve) - 1))]
        _node(d, px, py, int(7 * SS), WHITE)
    return o


def _motif_spreadsheet():
    """Outgrowing spreadsheets → grid of cells morphs into ERP nodes."""
    o, d = _overlay()
    cy = int(H2 * 0.5)
    # spreadsheet grid (left)
    gx, gy = int(W2 * 0.46), cy - int(90 * SS)
    cols, rows, cw, ch = 4, 4, int(48 * SS), int(40 * SS)
    _rr(d, [gx, gy, gx + cols * cw, gy + rows * ch], radius=10 * SS,
        fill=(255, 255, 255, 12), outline=SLATE + (200,), width=int(3 * SS))
    for c in range(1, cols):
        d.line([(gx + c * cw, gy), (gx + c * cw, gy + rows * ch)], fill=SLATE + (130,), width=int(2 * SS))
    for r in range(1, rows):
        d.line([(gx, gy + r * ch), (gx + cols * cw, gy + r * ch)], fill=SLATE + (130,), width=int(2 * SS))
    d.rectangle([gx, gy, gx + cols * cw, gy + ch], fill=BRAND + (50,))  # header row
    # arrow
    axs = gx + cols * cw + int(26 * SS)
    d.line([(axs, cy), (axs + int(70 * SS), cy)], fill=TEAL_LT + (255,), width=int(6 * SS))
    d.line([(axs + int(46 * SS), cy - int(22 * SS)), (axs + int(72 * SS), cy), (axs + int(46 * SS), cy + int(22 * SS))],
           fill=TEAL_LT + (255,), width=int(6 * SS), joint='curve')
    # ERP nodes (right): hub + spokes
    hx, hy = int(W2 * 0.84), cy
    spokes = [(hx, hy - int(110 * SS)), (hx + int(96 * SS), hy - int(20 * SS)),
              (hx + int(60 * SS), hy + int(96 * SS)), (hx - int(70 * SS), hy + int(70 * SS))]
    for s in spokes:
        d.line([(hx, hy), s], fill=TEAL + (170,), width=int(3 * SS))
    for s in spokes:
        _node(d, s[0], s[1], int(16 * SS), BRAND_LT)
    _node(d, hx, hy, int(30 * SS), TEAL_LT)
    return o


def _motif_default():
    """Generic ERP → connected node network."""
    o, d = _overlay()
    cx, cy = int(W2 * 0.68), int(H2 * 0.5)
    pts = [(cx, cy), (cx - int(150 * SS), cy - int(90 * SS)), (cx + int(140 * SS), cy - int(110 * SS)),
           (cx + int(160 * SS), cy + int(80 * SS)), (cx - int(120 * SS), cy + int(110 * SS))]
    for p in pts[1:]:
        d.line([pts[0], p], fill=TEAL + (170,), width=int(3 * SS))
    cols = [TEAL_LT, BRAND_LT, BRAND_LT, TEAL, BRAND_LT]
    for p, c in zip(pts, cols):
        _node(d, p[0], p[1], int(30 * SS) if p == pts[0] else int(16 * SS), c)
    return o


_MOTIFS = {
    'diagnostics': _motif_diagnostics,
    'modules': _motif_modules,
    'migration': _motif_migration,
    'upgrade': _motif_upgrade,
    'integration': _motif_integration,
    'spreadsheet': _motif_spreadsheet,
    'default': _motif_default,
}


def pick_motif(slug):
    s = (slug or '').lower()
    if 'spreadsheet' in s or 'outgrow' in s:
        return 'spreadsheet'
    if 'django' in s or 'integration' in s:
        return 'integration'
    if 'upgrade' in s or 'odoo-19' in s or 'move' in s:
        return 'upgrade'
    if 'migration' in s or 'migrate' in s:
        return 'migration'
    if 'studio' in s or 'module' in s:
        return 'modules'
    if 'health' in s or 'warning' in s or 'check' in s or 'sign' in s or 'diagnos' in s:
        return 'diagnostics'
    return 'default'


def render_cover(motif):
    base = _background()
    base.alpha_composite(_MOTIFS.get(motif, _motif_default)())
    _brand_furniture(base)
    return base.convert('RGB').resize((W, H), Image.LANCZOS)


class Command(BaseCommand):
    help = 'Generate original, on-brand PNG cover images for blog articles.'

    def add_arguments(self, parser):
        parser.add_argument('--slug', help='Only (re)generate the cover for this slug.')

    def handle(self, *args, **options):
        if Image is None:
            raise CommandError('Pillow is required: pip install Pillow')

        out_dir = Path(settings.BASE_DIR) / 'static' / 'img' / 'insights'
        out_dir.mkdir(parents=True, exist_ok=True)

        only = options.get('slug')
        posts = BlogPost.objects.all()
        if only:
            posts = posts.filter(slug=only)
            if not posts:
                raise CommandError('No article found with slug "%s".' % only)

        for post in posts:
            motif = pick_motif(post.slug)
            render_cover(motif).save(out_dir / ('%s.png' % post.slug), optimize=True)
            self.stdout.write('  cover: %s.png  [%s]' % (post.slug, motif))

        if not only:
            render_cover('default').save(out_dir / 'default.png', optimize=True)
            self.stdout.write('  cover: default.png  [default]')

        self.stdout.write(self.style.SUCCESS('Article covers generated (1200x630).'))
