"""ERP Rescue Check: scoring, flow, email, booking handoff, cross-links."""
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from core.models import EmailLog
from tool_erp_rescue.checklist import (
    QUESTION_CODES, QUESTIONS, compute_result, level_for,
)
from tools_core.models import Lead, ToolRun

ALL_HEALTHY = {code: ('yes' if not reverse else 'no')
               for code, _s, _w, reverse in QUESTIONS}
ALL_BAD = {code: ('no' if not reverse else 'yes')
           for code, _s, _w, reverse in QUESTIONS}


def form_payload(answers, **overrides):
    data = {'q_%s' % code: value for code, value in answers.items()}
    data.update({'email': 'cto@example.com', 'full_name': 'CTO',
                 'company': 'Acme', 'erp_type': 'odoo', 'consent': 'on'})
    data.update(overrides)
    return data


class ScoringTests(SimpleTestCase):
    def test_all_healthy_scores_zero_and_stable(self):
        result = compute_result(ALL_HEALTHY)
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['level'], 'stable')
        self.assertEqual(result['top_risks'], [])
        self.assertTrue(all(v == 0 for v in result['sections'].values()))

    def test_all_bad_scores_hundred_and_urgent(self):
        result = compute_result(ALL_BAD)
        self.assertEqual(result['score'], 100)
        self.assertEqual(result['level'], 'rescue_urgent')
        self.assertEqual(len(result['top_risks']), 3)

    def test_reverse_questions_score_correctly(self):
        answers = dict(ALL_HEALTHY)
        answers['parallel_excel'] = 'yes'   # reverse: yes = risk
        result = compute_result(answers)
        self.assertGreater(result['score'], 0)
        self.assertEqual(result['top_risks'], ['parallel_excel'])
        self.assertGreater(result['sections']['trust'], 0)
        self.assertEqual(result['sections']['people'], 0)

    def test_killer_questions_outrank_lighter_ones(self):
        answers = dict(ALL_HEALTHY)
        answers['tested_backup'] = 'no'     # weight 5
        answers['process_map'] = 'no'       # weight 2
        answers['single_developer'] = 'yes'  # weight 5 reverse
        result = compute_result(answers)
        self.assertEqual(set(result['top_risks'][:2]),
                         {'tested_backup', 'single_developer'})
        self.assertEqual(result['top_risks'][2], 'process_map')

    def test_partial_counts_half(self):
        answers = dict(ALL_HEALTHY)
        answers['reports_match'] = 'partial'
        full = dict(ALL_HEALTHY)
        full['reports_match'] = 'no'
        self.assertAlmostEqual(compute_result(answers)['sections']['trust'] * 2,
                               compute_result(full)['sections']['trust'], delta=1)

    def test_level_bands(self):
        self.assertEqual(level_for(0), 'stable')
        self.assertEqual(level_for(19), 'stable')
        self.assertEqual(level_for(20), 'needs_monitoring')
        self.assertEqual(level_for(45), 'at_risk')
        self.assertEqual(level_for(70), 'rescue_urgent')
        self.assertEqual(level_for(100), 'rescue_urgent')


@override_settings(ALLOWED_HOSTS=['testserver'],
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RescueFlowTests(TestCase):
    URL = '/en/tools/erp-rescue/'

    def setUp(self):
        cache.clear()  # the per-email daily rate limit lives in the cache

    def test_full_happy_path_creates_run_lead_and_email(self):
        response = self.client.post(self.URL, form_payload(ALL_BAD))
        run = ToolRun.objects.get(tool_slug='erp_rescue')
        self.assertRedirects(response, f'/en/tools/erp-rescue/result/{run.pk}/')

        self.assertEqual(run.status, 'done')
        self.assertEqual(run.result_json['rescue']['score'], 100)
        self.assertEqual(run.result_json['meta']['erp_type'], 'odoo')

        lead = Lead.objects.get(source_tool='erp_rescue')
        self.assertEqual(lead.email, 'cto@example.com')
        self.assertTrue(lead.consent_marketing)

        log = EmailLog.objects.get(category='rescue_check')
        self.assertEqual(log.status, 'sent')
        self.assertIn('100 / 100', log.text_body)
        self.assertIn(f'/tools/erp-rescue/result/{run.pk}/', log.text_body)
        self.assertIn('Studio X-Ray', log.text_body)  # odoo cross-sell
        self.assertTrue(any('Rescue Check results' in m.subject for m in mail.outbox))

    def test_non_odoo_email_has_no_xray_pitch(self):
        self.client.post(self.URL, form_payload(ALL_BAD, erp_type='other'))
        self.assertNotIn('Studio X-Ray',
                         EmailLog.objects.get(category='rescue_check').text_body)

    def test_missing_answer_rerenders_with_error(self):
        partial = dict(ALL_BAD)
        del partial['tested_backup']
        response = self.client.post(self.URL, form_payload(partial))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ToolRun.objects.count(), 0)
        self.assertContains(response, 'answer all the questions')

    def test_honeypot_redirects_without_saving(self):
        response = self.client.post(self.URL, form_payload(ALL_BAD, website='spam'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ToolRun.objects.count(), 0)

    def test_result_page_renders_score_risks_and_plan(self):
        self.client.post(self.URL, form_payload(ALL_BAD))
        run = ToolRun.objects.get()
        content = self.client.get(
            f'/en/tools/erp-rescue/result/{run.pk}/').content.decode()
        self.assertIn('Rescue needed urgently', content)
        self.assertIn('Your top 3 risks', content)
        self.assertIn('Your first rescue plan', content)
        self.assertIn('Run Studio X-Ray now', content)        # odoo CTA
        self.assertIn('Book my free rescue review', content)

    def test_xray_cta_hidden_for_non_odoo(self):
        self.client.post(self.URL, form_payload(ALL_BAD, erp_type='other'))
        run = ToolRun.objects.get()
        content = self.client.get(
            f'/en/tools/erp-rescue/result/{run.pk}/').content.decode()
        self.assertNotIn('Run Studio X-Ray now', content)
        self.assertIn('Book my free rescue review', content)

    def test_expired_result_shows_expiry_message(self):
        from datetime import timedelta
        from django.utils import timezone
        self.client.post(self.URL, form_payload(ALL_BAD))
        run = ToolRun.objects.get()
        ToolRun.objects.filter(pk=run.pk).update(
            expires_at=timezone.now() - timedelta(hours=1))
        content = self.client.get(
            f'/en/tools/erp-rescue/result/{run.pk}/').content.decode()
        self.assertIn('This result has expired', content)
        self.assertNotIn('Your top 3 risks', content)

    def test_booking_prefill_built_from_results(self):
        self.client.post(self.URL, form_payload(ALL_BAD))
        run = ToolRun.objects.get()
        response = self.client.get(f'/en/tools/erp-rescue/result/{run.pk}/book/')
        self.assertEqual(response.status_code, 302)
        prefill = self.client.session['booking_prefill']
        self.assertIn('100/100', prefill['problem_summary'])
        self.assertIn('Main risks:', prefill['problem_summary'])
        self.assertEqual(prefill['consultation_type'], 'intro_call')
        self.assertEqual(prefill['email'], 'cto@example.com')
        self.assertEqual(prefill['odoo_version'], 'Odoo')

    def test_landing_renders_all_questions(self):
        content = self.client.get(self.URL).content.decode()
        for code in QUESTION_CODES:
            self.assertIn('q_%s' % code, content)
        self.assertIn('rescueCheck()', content)

    def test_arabic_landing_renders(self):
        response = self.client.get('/ar/tools/erp-rescue/')
        self.assertEqual(response.status_code, 200)

    def test_hub_links_to_the_tool(self):
        content = self.client.get('/en/tools/').content.decode()
        self.assertIn('/en/tools/erp-rescue/', content)
        self.assertIn('ERP Rescue Check', content)


GOOD_ADVICE = ('{"advisor_reading": "Connected reading.", '
               '"next_3_steps": ["a", "b", "c"], '
               '"management_questions": ["q1", "q2", "q3"], '
               '"internal_sales_signal": "Lead with backups."}')


class AdvisorValidationTests(SimpleTestCase):
    def test_valid_payload_passes_and_is_capped(self):
        from tool_erp_rescue.advisor import validate_advice
        advice = validate_advice(GOOD_ADVICE)
        self.assertEqual(advice['advisor_reading'], 'Connected reading.')
        self.assertEqual(advice['next_3_steps'], ['a', 'b', 'c'])
        self.assertEqual(advice['internal_sales_signal'], 'Lead with backups.')

        long = ('{"advisor_reading": "%s", "next_3_steps": ["x","x","x","x","x"]}'
                % ('r' * 5000))
        advice = validate_advice(long)
        self.assertEqual(len(advice['advisor_reading']), 1200)
        self.assertEqual(len(advice['next_3_steps']), 3)   # capped at 3
        self.assertEqual(advice['management_questions'], [])

    def test_garbage_rejected(self):
        from tool_erp_rescue.advisor import validate_advice
        self.assertIsNone(validate_advice('not json'))
        self.assertIsNone(validate_advice('{"advisor_reading": "  "}'))
        self.assertIsNone(validate_advice('[1, 2]'))


@override_settings(ALLOWED_HOSTS=['testserver'], TOOLS_AI_MODEL='gemma4:26b',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AdvisorFlowTests(TestCase):
    URL = '/en/tools/erp-rescue/'
    DELAY = 'tool_erp_rescue.views.generate_advisor_reading.delay'

    def setUp(self):
        cache.clear()  # the per-email daily rate limit lives in the cache

    def _submit(self, **overrides):
        with mock.patch(self.DELAY) as delay:
            self.client.post(self.URL, form_payload(
                ALL_BAD, pain_text='We cannot close the month.', **overrides))
        return ToolRun.objects.get(), delay

    def test_submit_stores_pain_and_queues_advisor(self):
        run, delay = self._submit()
        meta = run.result_json['meta']
        self.assertEqual(meta['pain_text'], 'We cannot close the month.')
        self.assertEqual(meta['language'], 'en')
        self.assertEqual(run.result_json['advisor'], {'status': 'pending'})
        delay.assert_called_once_with(str(run.pk))

    def test_ai_disabled_means_no_advisor(self):
        with override_settings(TOOLS_AI_MODEL=''):
            run, delay = self._submit()
        self.assertIsNone(run.result_json['advisor'])
        delay.assert_not_called()

    def test_broker_down_marks_advisor_failed(self):
        with mock.patch(self.DELAY, side_effect=OSError('down')):
            self.client.post(self.URL, form_payload(ALL_BAD))
        run = ToolRun.objects.get()
        self.assertEqual(run.result_json['advisor'], {'status': 'failed'})

    def test_task_generates_and_stores_reading(self):
        from tool_erp_rescue.tasks import generate_advisor_reading
        run, _ = self._submit()
        with mock.patch('tool_erp_rescue.advisor.ai_service.generate_json',
                        return_value=GOOD_ADVICE) as gen:
            generate_advisor_reading(str(run.pk))
        run.refresh_from_db()
        advisor = run.result_json['advisor']
        self.assertEqual(advisor['status'], 'done')
        self.assertEqual(advisor['advisor_reading'], 'Connected reading.')
        self.assertEqual(advisor['internal_sales_signal'], 'Lead with backups.')
        # strict mode + grounded payload with the pain text and 24 answers
        self.assertFalse(gen.call_args.kwargs['allow_thinking'])
        import json as json_mod
        sent = json_mod.loads(gen.call_args[0][1])
        self.assertEqual(sent['pain_text'], 'We cannot close the month.')
        self.assertEqual(len(sent['questions']), 24)
        self.assertEqual(sent['score'], 100)

    def test_task_failure_marks_failed_and_keeps_result(self):
        from tool_erp_rescue.tasks import generate_advisor_reading
        run, _ = self._submit()
        with mock.patch('tool_erp_rescue.advisor.ai_service.generate_json',
                        return_value=None):
            generate_advisor_reading(str(run.pk))
        run.refresh_from_db()
        self.assertEqual(run.result_json['advisor'], {'status': 'failed'})
        self.assertEqual(run.result_json['rescue']['score'], 100)  # untouched

    def test_task_noop_when_not_pending(self):
        from tool_erp_rescue.tasks import generate_advisor_reading
        with override_settings(TOOLS_AI_MODEL=''):
            run, _ = self._submit()
        with mock.patch('tool_erp_rescue.advisor.ai_service.generate_json') as gen:
            generate_advisor_reading(str(run.pk))
        gen.assert_not_called()

    def test_status_endpoint_never_leaks_internal_signal(self):
        from tool_erp_rescue.tasks import generate_advisor_reading
        run, _ = self._submit()
        url = f'/en/tools/erp-rescue/result/{run.pk}/advisor/'
        self.assertEqual(self.client.get(url).json(), {'status': 'pending'})

        with mock.patch('tool_erp_rescue.advisor.ai_service.generate_json',
                        return_value=GOOD_ADVICE):
            generate_advisor_reading(str(run.pk))
        data = self.client.get(url).json()
        self.assertEqual(data['status'], 'done')
        self.assertEqual(data['advisor_reading'], 'Connected reading.')
        self.assertEqual(data['next_3_steps'], ['a', 'b', 'c'])
        self.assertNotIn('internal_sales_signal', data)

    def test_result_page_polls_when_pending_and_renders_when_done(self):
        from tool_erp_rescue.tasks import generate_advisor_reading
        run, _ = self._submit()
        page = self.client.get(f'/en/tools/erp-rescue/result/{run.pk}/').content.decode()
        self.assertIn('advisorCard(', page)
        self.assertIn('advisor/', page)

        with mock.patch('tool_erp_rescue.advisor.ai_service.generate_json',
                        return_value=GOOD_ADVICE):
            generate_advisor_reading(str(run.pk))
        page = self.client.get(f'/en/tools/erp-rescue/result/{run.pk}/').content.decode()
        self.assertIn('Connected reading.', page)
        self.assertIn('Questions to ask your team', page)
        self.assertNotIn('Lead with backups.', page)   # internal signal hidden
