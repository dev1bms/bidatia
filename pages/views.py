from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from core.seo import breadcrumb_ld, json_ld
from tools_core.services.analytics import track

from .odoo_versions import annotate, annotated_versions, get_version

EOL_TOOL = 'odoo_eol'


def privacy(request):
    return render(request, 'pages/privacy.html', {
        'meta_description': _('Bidatia privacy policy — how we collect, use and protect your data.'),
    })


def terms(request):
    return render(request, 'pages/terms.html', {
        'meta_description': _('Bidatia terms of service — the conditions for using our website and services.'),
    })


# ── Odoo version EOL countdown pages ─────────────────────────────────────────

def odoo_eol_index(request):
    versions = annotated_versions()
    track(request, EOL_TOOL, 'odoo_eol_page_view', version='index')
    return render(request, 'pages/odoo_eol_index.html', {
        'versions': versions,
        'meta_description': _(
            'Odoo version support timelines at a glance: which versions are '
            'still maintained, which are ending soon and which are past their '
            'window — with estimated dates and upgrade guidance.'
        ),
    })


def odoo_eol_detail(request, slug):
    version = get_version(slug)
    if version is None:
        raise Http404
    v = annotate(version)
    track(request, EOL_TOOL, 'odoo_eol_page_view', version=v['slug'])

    faq = _faq_items(v)
    context = {
        'v': v,
        'others': [o for o in annotated_versions() if o['slug'] != v['slug']],
        'faq': faq,
        'checklist': _checklist_items(),
        'meta_title': _('%(name)s support timeline & end-of-life countdown') % {'name': v['name']},
        'meta_description': _(
            '%(name)s support status, estimated end-of-support date, what it '
            'means for your business and how to prepare the upgrade — checked '
            'against Odoo\'s standard three-version maintenance policy.'
        ) % {'name': v['name']},
        'jsonld_blocks': [
            json_ld({
                '@context': 'https://schema.org',
                '@type': 'FAQPage',
                'mainEntity': [{
                    '@type': 'Question',
                    'name': str(item['q']),
                    'acceptedAnswer': {'@type': 'Answer', 'text': str(item['a'])},
                } for item in faq],
            }),
            json_ld(breadcrumb_ld(request, [
                (_('Odoo version support'), '/odoo-version-support/'),
                (v['name'], '/odoo-version-support/%s/' % v['slug']),
            ])),
        ],
    }
    return render(request, 'pages/odoo_eol_detail.html', context)


def eol_go_xray(request, slug):
    track(request, EOL_TOOL, 'odoo_eol_xray_clicked', version=slug)
    return redirect('tool_studio_xray:landing')


def eol_go_rescue(request, slug):
    track(request, EOL_TOOL, 'odoo_eol_rescue_clicked', version=slug)
    return redirect('tool_erp_rescue:landing')


def _faq_items(v):
    date_text = v['support_end'].strftime('%B %Y')
    if v['status'] == 'ended':
        when_answer = _(
            'Based on Odoo\'s standard three-version maintenance policy, the '
            '%(name)s window is estimated to have closed around %(date)s. '
            'Systems still on it keep working, but without official bug fixes '
            'or security patches from that point on.'
        ) % {'name': v['name'], 'date': date_text}
    else:
        when_answer = _(
            'Our planning estimate, based on Odoo\'s standard three-version '
            'maintenance policy, is around %(date)s. Odoo does not publish a '
            'fixed end-of-life date, so treat this as a planning horizon.'
        ) % {'date': date_text}
    return [
        {'q': _('When does %(name)s support end?') % {'name': v['name']},
         'a': when_answer},
        {'q': _('What happens when an Odoo version leaves the support window?'),
         'a': _('The system keeps running, but official bug fixes, security '
                'patches and standard migration scripts stop targeting it. '
                'Every month after that quietly raises the cost and risk of '
                'the eventual upgrade.')},
        {'q': _('Can we still upgrade from %(name)s?') % {'name': v['name']},
         'a': _('Yes — upgrades remain possible from any version, but the '
                'further behind you are, the more steps and the more custom-'
                'code rework the migration needs. An audit of your '
                'customizations is the single best preparation.')},
        {'q': _('How long does an Odoo version upgrade usually take?'),
         'a': _('Anywhere from days to months — it depends almost entirely on '
                'how many customizations, integrations and data quality '
                'issues your database carries. That is measurable before you '
                'commit to anything.')},
    ]


def _checklist_items():
    return [
        _('Inventory every customization: Studio fields, custom models, automations and code modules.'),
        _('Find out which customizations are actually used — and which are abandoned.'),
        _('List your integrations and check each one against the target version.'),
        _('Clean master data before migrating, not after.'),
        _('Test the upgrade on a copy of production first — never in place.'),
        _('Plan the cutover window with the people who run daily operations.'),
    ]
