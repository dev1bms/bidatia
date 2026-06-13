from django.test import TestCase, override_settings

from tool_studio_xray.tests.test_views import make_done_run
from tool_studio_xray.views import _review_agenda
from tools_core.models import Lead


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReviewAgendaTests(TestCase):
    def test_agenda_built_from_stored_results(self):
        run = make_done_run()
        agenda = _review_agenda(run.result_json)
        text = ' '.join(agenda)
        self.assertIn('37/100', text)                      # score + band line
        self.assertIn('2 Studio-created models', text)     # custom models
        self.assertIn('Odoo 17 to Odoo 19', text)          # upgrade gap line
        self.assertLessEqual(len(agenda), 5)

    def test_minimal_agenda_for_wiped_results(self):
        agenda = _review_agenda(None)
        self.assertEqual(len(agenda), 1)
        self.assertIn('Studio X-Ray', agenda[0])


@override_settings(ALLOWED_HOSTS=['testserver'])
class BookReviewHandoffTests(TestCase):
    def _run_with_lead(self):
        lead = Lead.objects.create(
            email='cto@example.com', source_tool='studio_xray',
            full_name='Jane CTO', company='Boss Continental')
        run = make_done_run(lead=lead)
        return run

    def test_handoff_fills_session_and_redirects_to_booking(self):
        run = self._run_with_lead()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/book/')
        self.assertRedirects(resp, '/en/book-consultation/',
                             fetch_redirect_response=False)
        prefill = self.client.session['booking_prefill']
        self.assertEqual(prefill['full_name'], 'Jane CTO')
        self.assertEqual(prefill['company_name'], 'Boss Continental')
        self.assertEqual(prefill['email'], 'cto@example.com')
        self.assertEqual(prefill['consultation_type'], 'intro_call')
        self.assertEqual(prefill['odoo_version'], 'Odoo 17.0')
        summary = prefill['problem_summary']
        self.assertIn('Suggested agenda:', summary)
        self.assertIn('• ', summary)
        self.assertIn(f'/tools/studio-xray/report/{run.pk}/', summary)
        self.assertIn('free 30-minute review', summary)

    @override_settings(TOOLS_BOOKING_URL='https://calendly.com/bidatia/30min')
    def test_external_booking_url_takes_precedence(self):
        run = self._run_with_lead()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/book/')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers['Location'], 'https://calendly.com/bidatia/30min')

    def test_wiped_run_still_hands_off_with_minimal_agenda(self):
        run = make_done_run(result_json=None)
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/book/')
        self.assertEqual(resp.status_code, 302)
        summary = self.client.session['booking_prefill']['problem_summary']
        self.assertIn('Report link:', summary)

    def test_booking_form_consumes_the_prefill_once(self):
        run = self._run_with_lead()
        self.client.get(f'/en/tools/studio-xray/report/{run.pk}/book/')
        resp = self.client.get('/en/book-consultation/')
        content = resp.content.decode()
        self.assertIn('Suggested agenda:', content)        # textarea prefilled
        self.assertIn('cto@example.com', content)          # identity prefilled
        self.assertIn('Boss Continental', content)
        self.assertIn('Odoo 17.0', content)
        # one-shot: a fresh visit is clean again
        resp2 = self.client.get('/en/book-consultation/')
        self.assertNotIn('Suggested agenda:', resp2.content.decode())

    def test_report_page_shows_the_agenda_card(self):
        run = self._run_with_lead()
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        content = resp.content.decode()
        self.assertIn('Your free review agenda is ready', content)
        self.assertIn('pre-fill the booking form', content)
        self.assertIn(f'/tools/studio-xray/report/{run.pk}/book/', content)
        self.assertIn('Studio-created models', content)    # agenda bullet visible
