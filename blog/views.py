from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _

from core.admin_links import admin_change_link
from core.seo import absolute_url, article_ld, breadcrumb_ld, json_ld

from .covers import cover_url
from .models import BlogPost, CaseStudy


def blog_list(request):
    posts = BlogPost.objects.filter(is_published=True)
    context = {
        'posts': posts,
        'meta_description': _(
            'Practical insights on Odoo, ERP automation, Django integrations and business '
            'technology — written by BidERP, Madrid.'
        ),
    }
    return render(request, 'blog/blog_list.html', context)


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    # Absolute URL of this article's cover, used for both the JSON-LD image and
    # the per-article Open Graph / Twitter social card.
    og_image = absolute_url(request, cover_url(post))
    context = {
        'post': post,
        'og_image': og_image,
        'admin_edit': admin_change_link(request, post, _('Edit this insight')),
        'meta_description': post.meta_description or post.excerpt,
        'jsonld_blocks': [
            json_ld(article_ld(request, post, image_url=og_image)),
            json_ld(breadcrumb_ld(request, [
                (_('Home'), reverse('core:home')),
                (_('Insights'), reverse('blog:blog_list')),
                (post.title, post.get_absolute_url()),
            ])),
        ],
    }
    return render(request, 'blog/blog_detail.html', context)


def case_study_list(request):
    case_studies = CaseStudy.objects.filter(is_published=True)
    context = {
        'case_studies': case_studies,
        'meta_description': _(
            'Real Odoo and ERP technical projects delivered by BidERP — audits, cleanups, '
            'migrations, integrations and ongoing support, with measurable results.'
        ),
    }
    return render(request, 'case_studies/list.html', context)


def case_study_detail(request, slug):
    case_study = get_object_or_404(CaseStudy, slug=slug, is_published=True)
    context = {
        'case_study': case_study,
        'admin_edit': admin_change_link(request, case_study, _('Edit this case study')),
        'meta_description': case_study.meta_description or case_study.client_summary,
        'jsonld_blocks': [
            json_ld(breadcrumb_ld(request, [
                (_('Home'), reverse('core:home')),
                (_('Case Studies'), reverse('case_studies:case_study_list')),
                (case_study.title, case_study.get_absolute_url()),
            ])),
        ],
    }
    return render(request, 'case_studies/detail.html', context)
