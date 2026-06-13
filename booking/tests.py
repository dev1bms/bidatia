from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from booking.forms import SlotGeneratorForm
from booking.models import AvailabilitySlot

GEN_URL = '/admin/booking/availabilityslot/generate-slots/'


def _base_data(**overrides):
    data = {
        'consultation_type': 'intro_call',
        'start_date': '2030-01-07',   # single day, all weekdays selected
        'end_date': '2030-01-07',
        'weekdays': ['0', '1', '2', '3', '4', '5', '6'],
        'start_time': '09:00',
        'end_time': '12:00',
        'slot_minutes': 60,
        'gap_minutes': 0,
        'timezone': 'Europe/Madrid',
        'is_active': True,
    }
    data.update(overrides)
    return data


class SlotGeneratorFormTests(TestCase):
    def test_generates_expected_slots(self):
        form = SlotGeneratorForm(data=_base_data())
        self.assertTrue(form.is_valid(), form.errors)
        created, skipped = form.generate()
        self.assertEqual((created, skipped), (3, 0))  # 09-10, 10-11, 11-12
        self.assertEqual(AvailabilitySlot.objects.count(), 3)

    def test_skips_duplicates_on_rerun(self):
        first = SlotGeneratorForm(data=_base_data())
        self.assertTrue(first.is_valid(), first.errors)
        first.generate()
        second = SlotGeneratorForm(data=_base_data())
        self.assertTrue(second.is_valid(), second.errors)
        created, skipped = second.generate()
        self.assertEqual((created, skipped), (0, 3))
        self.assertEqual(AvailabilitySlot.objects.count(), 3)

    def test_duration_and_gap(self):
        # 09:00–11:00, 30-min slots, 15-min gap -> 09:00, 09:45, 10:30 = 3
        form = SlotGeneratorForm(data=_base_data(
            start_time='09:00', end_time='11:00', slot_minutes=30, gap_minutes=15))
        self.assertTrue(form.is_valid(), form.errors)
        created, _ = form.generate()
        self.assertEqual(created, 3)

    def test_multi_day_weekday_filter(self):
        # Full week, only Mondays + Wednesdays, two 1-hour slots/day.
        form = SlotGeneratorForm(data=_base_data(
            start_date='2030-01-07', end_date='2030-01-13',  # Mon..Sun
            weekdays=['0', '2'], start_time='09:00', end_time='11:00', slot_minutes=60))
        self.assertTrue(form.is_valid(), form.errors)
        created, _ = form.generate()
        self.assertEqual(created, 4)  # 2 days x 2 slots

    def test_validation_rules(self):
        self.assertFalse(SlotGeneratorForm(data=_base_data(end_date='2030-01-06')).is_valid())
        self.assertFalse(SlotGeneratorForm(data=_base_data(end_time='09:00')).is_valid())
        self.assertFalse(SlotGeneratorForm(data=_base_data(slot_minutes=600)).is_valid())
        self.assertFalse(SlotGeneratorForm(data=_base_data(weekdays=[])).is_valid())
        self.assertFalse(SlotGeneratorForm(data=_base_data(slot_minutes=0)).is_valid())


@override_settings(ALLOWED_HOSTS=['testserver'])
class SlotGeneratorAdminViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'staff', 'staff@bidatia.xyz', 'x')

    def test_anonymous_is_redirected_to_login(self):
        resp = self.client.get(GEN_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])

    def test_get_renders_form(self):
        self.client.force_login(self.admin)
        resp = self.client.get(GEN_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Generate slots')

    def test_post_creates_slots_and_reports(self):
        self.client.force_login(self.admin)
        resp = self.client.post(GEN_URL, data=_base_data(), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AvailabilitySlot.objects.count(), 3)
        self.assertContains(resp, 'created')

    def test_invalid_post_shows_errors_creates_nothing(self):
        self.client.force_login(self.admin)
        resp = self.client.post(GEN_URL, data=_base_data(end_time='09:00'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)

    def test_get_prefilled_from_query_params(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            GEN_URL + '?start_date=2030-01-07&end_date=2030-01-07&weekdays=0&consultation_type=intro_call')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'value="2030-01-07"')  # date pre-filled


@override_settings(ALLOWED_HOSTS=['testserver'], LANGUAGE_CODE='en')
class SlotAdminActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'staff2', 'staff2@bidatia.xyz', 'x')

    def test_delete_unbooked_future_keeps_booked_and_past(self):
        self.client.force_login(self.admin)
        today = timezone.localdate()
        future_unbooked = AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=today + timedelta(days=3),
            start_time=time(9, 0), end_time=time(9, 30))
        future_booked = AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=today + timedelta(days=3),
            start_time=time(10, 0), end_time=time(10, 30), is_booked=True)
        past_unbooked = AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=today - timedelta(days=3),
            start_time=time(9, 0), end_time=time(9, 30))

        self.client.post('/admin/booking/availabilityslot/', {
            'action': 'delete_unbooked_future',
            '_selected_action': [future_unbooked.pk, future_booked.pk, past_unbooked.pk],
        }, follow=True)

        self.assertFalse(AvailabilitySlot.objects.filter(pk=future_unbooked.pk).exists())
        self.assertTrue(AvailabilitySlot.objects.filter(pk=future_booked.pk).exists())
        self.assertTrue(AvailabilitySlot.objects.filter(pk=past_unbooked.pk).exists())

    def test_changelist_renders_with_status_pill(self):
        self.client.force_login(self.admin)
        AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=timezone.localdate() + timedelta(days=1),
            start_time=time(9, 0), end_time=time(9, 30))
        resp = self.client.get('/admin/booking/availabilityslot/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Available')  # status pill text
        self.assertContains(resp, 'Free 20-minute Intro Call')  # readable type name

    def test_mark_unavailable_action(self):
        self.client.force_login(self.admin)
        slot = AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=timezone.localdate() + timedelta(days=2),
            start_time=time(9, 0), end_time=time(9, 30), is_active=True)
        self.client.post('/admin/booking/availabilityslot/', {
            'action': 'mark_unavailable',
            '_selected_action': [slot.pk],
        }, follow=True)
        slot.refresh_from_db()
        self.assertFalse(slot.is_active)


@override_settings(ALLOWED_HOSTS=['testserver'], LANGUAGE_CODE='en')
class SlotCalendarViewTests(TestCase):
    CAL_URL = '/admin/booking/availabilityslot/calendar/'

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('cal', 'cal@bidatia.xyz', 'x')

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.CAL_URL)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])

    def test_calendar_renders_current_month_slot(self):
        self.client.force_login(self.admin)
        AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=timezone.localdate(),
            start_time=time(9, 0), end_time=time(9, 30))
        resp = self.client.get(self.CAL_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '09:00')          # slot chip
        self.assertContains(resp, 'Total')          # summary
        self.assertContains(resp, 'cal-grid')       # calendar grid rendered

    def test_calendar_month_navigation(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.CAL_URL + '?year=2030&month=1')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'January 2030')

    def test_calendar_invalid_month_falls_back(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.CAL_URL + '?year=abc&month=99')
        self.assertEqual(resp.status_code, 200)

    def test_week_view_renders_hours_grid(self):
        self.client.force_login(self.admin)
        d = timezone.localdate()
        AvailabilitySlot.objects.create(
            consultation_type='intro_call', date=d, start_time=time(10, 0), end_time=time(10, 30))
        resp = self.client.get(self.CAL_URL + '?view=week&date=' + d.isoformat())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'wk-grid')   # week grid rendered
        self.assertContains(resp, '10:00')     # the slot appears

    def test_week_view_invalid_date_falls_back(self):
        self.client.force_login(self.admin)
        resp = self.client.get(self.CAL_URL + '?view=week&date=not-a-date')
        self.assertEqual(resp.status_code, 200)


@override_settings(ALLOWED_HOSTS=['testserver'])
class BookingPhoneFieldTests(TestCase):
    URL = '/en/book-consultation/'

    def test_phone_widget_present_with_default_country(self):
        resp = self.client.get(self.URL)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'intlTelInput')      # widget script loaded
        self.assertContains(resp, 'id="id_phone"')     # bound to the phone field
        self.assertContains(resp, "initialCountry: 'es'")  # fallback country

    def test_country_autodetected_from_cloudflare_header(self):
        resp = self.client.get(self.URL, HTTP_CF_IPCOUNTRY='SA')
        self.assertContains(resp, "initialCountry: 'sa'")

    def test_invalid_cf_country_falls_back_to_es(self):
        resp = self.client.get(self.URL, HTTP_CF_IPCOUNTRY='XX')
        self.assertContains(resp, "initialCountry: 'es'")

    def test_phone_control_forced_ltr_on_arabic_page(self):
        # The phone widget must stay LTR even on the RTL Arabic page so the flag,
        # dial code and number read in natural international order. The field is
        # wrapped in a forced-LTR container and the page carries scoped overrides
        # that restore intl-tel-input's own LTR layout.
        resp = self.client.get('/ar/book-consultation/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="booking-phone-field" dir="ltr"')
        self.assertContains(
            resp,
            '[dir="rtl"] .booking-phone-field .iti--allow-dropdown .iti__country-container',
        )

    def test_phone_field_wrapper_present_on_english_page(self):
        # The forced-LTR wrapper is present on the LTR pages too (a harmless
        # no-op there); the RTL-only overrides simply do not apply.
        resp = self.client.get('/en/book-consultation/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="booking-phone-field" dir="ltr"')
