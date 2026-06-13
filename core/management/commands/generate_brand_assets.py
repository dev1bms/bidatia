"""Generate the Bidatia brand image assets: Open Graph / social cards and the
favicon / app-icon set — deterministically, with Pillow, so nothing depends on
external design files or third-party brand assets.

What it produces
----------------
* static/img/og.png                 1200x630 default social card (homepage etc.)
* static/img/og-tools-hub.png       1200x630 Free Tools hub card
* static/img/og-studio-xray.png     1200x630 Studio X-Ray tool card
* static/img/og-erp-rescue.png      1200x630 ERP Rescue tool card
* static/icons/favicon-96x96.png            96x96  favicon
* static/icons/apple-touch-icon.png         180x180 iOS home-screen icon
* static/icons/web-app-manifest-192x192.png 192x192 PWA icon
* static/icons/web-app-manifest-512x512.png 512x512 PWA icon
* static/icons/favicon.ico                  multi-size .ico (16/32/48)

All assets share one visual system (slate canvas, anchor blue, governance green,
the red→green→blue "RGB" accent), reusing the cover renderer's helpers so the
blog covers and social cards stay perfectly consistent.

Usage
-----
    python manage.py generate_brand_assets
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - Pillow is a project dependency
    Image = None

from blog.management.commands.generate_article_covers import (
    BRAND, BRAND_LT, H, H2, INK, SLATE, SS, TEAL_LT, W, W2, WHITE,
    _MOTIFS, _background, _brand_furniture, _databars, _f, _signal_rule, _rr,
)


def _headline(base, title, subtitle):
    """Draw a large headline + subtitle on the left half of an OG card."""
    d = ImageDraw.Draw(base)
    x = int(64 * SS)
    y = int(H2 * 0.40)
    hf = _f(58)
    for i, line in enumerate(title):
        d.text((x, y + i * int(70 * SS)), line, font=hf, fill=WHITE,
               stroke_width=int(SS), stroke_fill=WHITE)
    sf = _f(26)
    d.text((x, y + len(title) * int(70 * SS) + int(14 * SS)), subtitle,
           font=sf, fill=BRAND_LT)


def _social_card(motif, title, subtitle):
    base = _background()
    base.alpha_composite(_MOTIFS.get(motif, _MOTIFS['default'])())
    _brand_furniture(base)
    _headline(base, title, subtitle)
    return base.convert('RGB').resize((W, H), Image.LANCZOS)


def _app_icon(size):
    """A squared Bidatia app icon: ink tile with the data-bars glyph."""
    s = size * SS
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = int(s * 0.16)
    _rr(d, [0, 0, s - 1, s - 1], radius=radius, fill=INK + (255,))
    # three ascending data bars (lime, lime, violet), centered.
    base = int(s * 0.74); pad = int(s * 0.24)
    bw = int(s * 0.13); gap = int(s * 0.095)
    hs = [int(s * 0.26), int(s * 0.40), int(s * 0.54)]
    cols = [TEAL_LT, TEAL_LT, BRAND_LT]
    total = 3 * bw + 2 * gap
    bx = int((s - total) / 2)
    for h, c in zip(hs, cols):
        d.rectangle([bx, base - h, bx + bw, base], fill=c + (255,))
        bx += bw + gap
    return img.resize((size, size), Image.LANCZOS)


class Command(BaseCommand):
    help = 'Generate Bidatia Open Graph / social cards and the favicon / app-icon set.'

    def handle(self, *args, **options):
        if Image is None:
            raise CommandError('Pillow is required: pip install Pillow')

        img_dir = Path(settings.BASE_DIR) / 'static' / 'img'
        ico_dir = Path(settings.BASE_DIR) / 'static' / 'icons'
        img_dir.mkdir(parents=True, exist_ok=True)
        ico_dir.mkdir(parents=True, exist_ok=True)

        cards = [
            ('og.png', 'default',
             ['Business systems', 'on data you', 'can trust'],
             'ERP · Odoo · Data governance · BI · AI'),
            ('og-tools-hub.png', 'diagnostics',
             ['Free ERP &', 'Odoo diagnostics'],
             'Scan, score and prioritize — in minutes'),
            ('og-studio-xray.png', 'modules',
             ['Odoo Studio', 'X-Ray'],
             'See every Studio customization, scored'),
            ('og-erp-rescue.png', 'default',
             ['ERP Rescue', 'diagnostic'],
             'A clear, prioritized recovery plan'),
        ]
        for name, motif, title, subtitle in cards:
            _social_card(motif, title, subtitle).save(img_dir / name, optimize=True)
            self.stdout.write('  card:  %s  [%s]' % (name, motif))

        icons = [
            ('favicon-96x96.png', 96),
            ('apple-touch-icon.png', 180),
            ('web-app-manifest-192x192.png', 192),
            ('web-app-manifest-512x512.png', 512),
        ]
        for name, size in icons:
            _app_icon(size).save(ico_dir / name, optimize=True)
            self.stdout.write('  icon:  %s  (%dx%d)' % (name, size, size))

        # Multi-resolution .ico from a single 256 master.
        master = _app_icon(256)
        master.save(ico_dir / 'favicon.ico', sizes=[(16, 16), (32, 32), (48, 48)])
        self.stdout.write('  icon:  favicon.ico  (16/32/48)')

        self.stdout.write(self.style.SUCCESS('Brand assets generated.'))
