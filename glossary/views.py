"""Odoo glossary — Arabic-first SEO asset (growth plan Phase 6).

Content lives in data.py (per-language fields); these views only group,
localize and decorate it with category labels, JSON-LD and analytics.
"""
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from core.seo import breadcrumb_ld, json_ld
from tools_core.services.analytics import track

from .data import get_term, localized, terms_by_category

GLOSSARY_TOOL = 'glossary'

CATEGORY_LABELS = {
    'studio': gettext_lazy('Odoo Studio'),
    'automation': gettext_lazy('Automations & scheduled jobs'),
    'orm': gettext_lazy('Models & data'),
    'views': gettext_lazy('Views & XML'),
    'core': gettext_lazy('Core concepts'),
    'accounting': gettext_lazy('Accounting & invoicing'),
    'sales': gettext_lazy('Sales & CRM'),
    'inventory': gettext_lazy('Inventory'),
    'migration': gettext_lazy('Migration & upgrades'),
    'hosting': gettext_lazy('Hosting & Odoo.sh'),
    'security': gettext_lazy('Security & access rights'),
    'integration': gettext_lazy('Integrations & API'),
}


def index(request):
    language = get_language() or 'en'
    track(request, GLOSSARY_TOOL, 'glossary_index_view')
    sections = [
        {
            'code': category,
            'label': CATEGORY_LABELS.get(category, category),
            'terms': [localized(t, language) for t in terms],
        }
        for category, terms in terms_by_category().items()
    ]
    return render(request, 'glossary/index.html', {
        'sections': sections,
        'term_total': sum(len(s['terms']) for s in sections),
        'meta_description': _(
            'Odoo & ERP glossary in plain language: Studio, custom fields, '
            'automations, migrations, hosting and security terms — what they '
            'mean, why they matter and the mistakes to avoid.'
        ),
    })


def term_detail(request, slug):
    term = get_term(slug)
    if term is None:
        raise Http404
    language = get_language() or 'en'
    data = localized(term, language)
    track(request, GLOSSARY_TOOL, 'glossary_term_view', term=slug)

    return render(request, 'glossary/term.html', {
        't': data,
        'category_label': CATEGORY_LABELS.get(data['category'], data['category']),
        'meta_title': _('%(term)s — meaning in Odoo, examples and common mistakes')
                      % {'term': data['title']},
        'meta_description': (data['definition'][:155] + '…'
                             if len(data['definition']) > 156 else data['definition']),
        'jsonld_blocks': [
            json_ld({
                '@context': 'https://schema.org',
                '@type': 'DefinedTerm',
                'name': data['title'],
                'description': data['definition'],
                'inDefinedTermSet': {
                    '@type': 'DefinedTermSet',
                    'name': 'Bidatia Odoo Glossary',
                },
            }),
            json_ld(breadcrumb_ld(request, [
                (_('Odoo glossary'), '/odoo-glossary/'),
                (data['title'], '/odoo-glossary/%s/' % slug),
            ])),
        ],
    })


def go_tool(request, slug):
    """Tracked CTA hand-off from a term page to the matching tool."""
    term = get_term(slug)
    if term is None:
        raise Http404
    track(request, GLOSSARY_TOOL, 'glossary_tool_cta_clicked',
          term=slug, cta=term['cta'] or 'xray')
    if term['cta'] == 'rescue':
        return redirect('tool_erp_rescue:landing')
    return redirect('tool_studio_xray:landing')
