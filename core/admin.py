"""Admin branding, the lightweight Unfold dashboard callback, and the
outgoing-email archive (core.EmailLog)."""
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from core.models import EmailLog

# Branding fallback (Unfold also reads UNFOLD['SITE_*'] in settings).
admin.site.site_header = 'Bidatia'
admin.site.site_title = 'Bidatia Business Systems'
admin.site.index_title = 'Dashboard'


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    """Read-only archive of every email the system sent (or failed to send).

    Rows are created exclusively by core.email_service; nothing here is
    editable — a sent message is a historical fact. Deletion stays allowed
    for cleanup.
    """
    list_display = ('created_at', 'category', 'recipient_email', 'subject',
                    'status', 'sent_at')
    list_filter = ('status', 'category', 'created_at')
    search_fields = ('recipient_email', 'recipient_name', 'subject')
    date_hierarchy = 'created_at'

    fields = ('created_at', 'sent_at', 'status', 'error_message',
              'category', 'recipient_email', 'recipient_name', 'subject',
              'related_type', 'related_id', 'metadata',
              'html_preview', 'text_body', 'html_body')
    readonly_fields = [f for f in fields if f != 'html_body'] + ['html_body']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # view-only; the archive must stay faithful

    @admin.display(description='HTML preview')
    def html_preview(self, obj):
        if not obj.html_body:
            return '—'
        # srcdoc is escaped by format_html and the iframe is fully sandboxed,
        # so archived HTML renders without ever executing in the admin.
        return format_html(
            '<iframe srcdoc="{}" sandbox style="width:100%;max-width:640px;'
            'height:520px;border:1px solid #e2e8f0;border-radius:8px;'
            'background:#f1f5f9;"></iframe>',
            obj.html_body,
        )


def dashboard_callback(request, context):
    """Inject lightweight business KPIs + recent activity into the admin index.

    Only a handful of cheap COUNT queries plus two small "5 most recent" lists,
    so the dashboard adds negligible load. Wired via UNFOLD['DASHBOARD_CALLBACK'].
    """
    # Imported here (not at module load) to avoid any app-registry ordering issues.
    from blog.models import BlogPost, CaseStudy
    from booking.models import AvailabilitySlot, ConsultationRequest
    from leads.models import Lead
    from services.models import Service

    today = timezone.localdate()

    kpis = [
        {
            'title': 'New consultation requests',
            'value': ConsultationRequest.objects.filter(status='new').count(),
            'link': reverse('admin:booking_consultationrequest_changelist') + '?status__exact=new',
        },
        {
            'title': 'Unhandled leads',
            'value': Lead.objects.filter(is_handled=False).count(),
            'link': reverse('admin:leads_lead_changelist') + '?is_handled__exact=0',
        },
        {
            'title': 'Upcoming open slots',
            'value': AvailabilitySlot.objects.filter(
                is_active=True, is_booked=False, date__gte=today).count(),
            'link': reverse('admin:booking_availabilityslot_changelist'),
        },
        {
            'title': 'Published services',
            'value': Service.objects.filter(is_published=True).count(),
            'link': reverse('admin:services_service_changelist'),
        },
        {
            'title': 'Published insights',
            'value': BlogPost.objects.filter(is_published=True).count(),
            'link': reverse('admin:blog_blogpost_changelist'),
        },
        {
            'title': 'Published case studies',
            'value': CaseStudy.objects.filter(is_published=True).count(),
            'link': reverse('admin:blog_casestudy_changelist'),
        },
    ]

    context.update({
        'dbms_kpis': kpis,
        'dbms_recent_consultations': ConsultationRequest.objects.order_by('-created_at')[:5],
        'dbms_recent_leads': Lead.objects.order_by('-created_at')[:5],
    })
    return context
