import json
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from tool_studio_xray.insights import _validated, build_payload, generate_insights
from tool_studio_xray.tests.test_views import make_done_run
from tools_core.services import ai_service

AI_ON = override_settings(TOOLS_AI_MODEL='qwen3.5:9b')

ANALYSIS = {
    'findings': [
        {'code': 'custom_studio_models', 'severity': 'critical', 'count': 99,
         'title': 't', 'detail': 'd', 'examples': []},
    ],
    'totals': {'studio_fields': 1719, 'custom_models': 99},
    'model_breakdown': [{'model': 'x_air_waybill', 'fields': 38, 'views': 0,
                         'automations': 1, 'total': 39}] * 20,
    'sections_with_errors': [],
    'module_summary': {
        'installed_total': 289, 'studio_installed': True,
        'by_origin': {'official': 268, 'oca': 1, 'third_party': 20, 'custom': 0},
        'non_standard_total': 21,
        'examples': {'oca': ['Partner first name'],
                     'third_party': ['Boss Cargo Insurance Wizard'], 'custom': []},
    },
}
SCORING = {'score': 100, 'effort_estimate': '4+ weeks'}
META = {'server_version': '17.0', 'edition': 'enterprise'}


def fake_stream(*chunks):
    """Context-manager + iterable standing in for urlopen's NDJSON stream."""
    lines = [json.dumps(c).encode() + b'\n' for c in chunks]
    stream = mock.MagicMock()
    stream.__enter__.return_value = iter(lines)
    stream.__exit__.return_value = False
    return stream


class AiServiceTests(SimpleTestCase):
    def test_disabled_by_default(self):
        self.assertFalse(ai_service.is_enabled())
        self.assertIsNone(ai_service.generate_json('sys', 'user'))

    @AI_ON
    def test_streamed_generation_accumulates_content_and_thinking(self):
        stream = fake_stream(
            {'message': {'thinking': 'The model names suggest '}},
            {'message': {'thinking': 'a logistics operation…'}},
            {'message': {'content': '{"narrative":'}},
            {'message': {'content': ' "ok"}'}, 'done': True},
        )
        notes = []
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=stream) as urlopen, \
                mock.patch('tools_core.services.ai_service.THINKING_CALLBACK_INTERVAL', 0):
            content = ai_service.generate_json('sys', 'user', on_thinking=notes.append)
        self.assertEqual(content, '{"narrative": "ok"}')
        self.assertEqual(notes[-1], 'The model names suggest a logistics operation…')
        request = urlopen.call_args[0][0]
        body = json.loads(request.data.decode())
        self.assertEqual(body['model'], 'qwen3.5:9b')
        # free-form first attempt: format=json + thinking yields empty content
        self.assertNotIn('format', body)
        self.assertTrue(body['stream'])
        self.assertIn('127.0.0.1:11434', request.full_url)

    @AI_ON
    def test_any_failure_returns_none(self):
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=OSError('down')):
            self.assertIsNone(ai_service.generate_json('sys', 'user'))

    @AI_ON
    @override_settings(TOOLS_AI_TIMEOUT=0)
    def test_deadline_exceeded_returns_none_without_retry(self):
        stream = fake_stream({'message': {'content': '{"narrative": "late"}'}, 'done': True})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=stream) as urlopen:
            self.assertIsNone(ai_service.generate_json('sys', 'user'))
        # no budget left -> no second attempt
        self.assertEqual(urlopen.call_count, 1)

    @AI_ON
    def test_empty_content_retries_with_thinking_disabled(self):
        # Reasoning models can burn the whole token budget thinking and emit
        # no answer — the production bug behind 'model returned empty content'.
        thinking_only = fake_stream({'message': {'thinking': 'all budget spent…'}, 'done': True})
        answer = fake_stream({'message': {'content': '{"narrative": "saved"}'}, 'done': True})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=[thinking_only, answer]) as urlopen:
            content = ai_service.generate_json('sys', 'user')
        self.assertEqual(content, '{"narrative": "saved"}')
        self.assertEqual(urlopen.call_count, 2)
        first_body = json.loads(urlopen.call_args_list[0][0][0].data.decode())
        retry_body = json.loads(urlopen.call_args_list[1][0][0].data.decode())
        self.assertNotIn('think', first_body)        # default (thinking on)
        self.assertNotIn('format', first_body)       # free-form answer allowed
        self.assertIs(retry_body['think'], False)    # retry answers directly
        self.assertEqual(retry_body['format'], 'json')  # ...and strictly

    @AI_ON
    def test_empty_on_both_attempts_returns_none(self):
        streams = [fake_stream({'message': {'thinking': 't'}, 'done': True}),
                   fake_stream({'message': {'thinking': 't'}, 'done': True})]
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=streams) as urlopen:
            self.assertIsNone(ai_service.generate_json('sys', 'user'))
        self.assertEqual(urlopen.call_count, 2)


def fake_response(payload):
    """Non-streaming urlopen stand-in exposing .read() + context manager."""
    resp = mock.MagicMock()
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    resp.read.return_value = json.dumps(payload).encode()
    return resp


class AiDiagnosticsTests(SimpleTestCase):
    """list_models / health_check / self_test power the admin AI panel + button."""

    def test_list_models_returns_sorted_names(self):
        resp = fake_response({'models': [{'name': 'qwen3.5:9b'}, {'name': 'gemma2:27b'}]})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=resp):
            self.assertEqual(ai_service.list_models(), ['gemma2:27b', 'qwen3.5:9b'])

    @AI_ON
    def test_health_check_flags_model_present(self):
        resp = fake_response({'models': [{'name': 'qwen3.5:9b'}, {'name': 'llama3'}]})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=resp):
            h = ai_service.health_check()
        self.assertTrue(h['reachable'])
        self.assertTrue(h['model_present'])          # configured qwen3.5:9b is pulled
        self.assertIn('llama3', h['models'])

    @override_settings(TOOLS_AI_MODEL='not-pulled:1b')
    def test_health_check_flags_missing_model(self):
        resp = fake_response({'models': [{'name': 'qwen3.5:9b'}]})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=resp):
            h = ai_service.health_check()
        self.assertTrue(h['reachable'])
        self.assertFalse(h['model_present'])

    def test_health_check_handles_unreachable(self):
        import urllib.error
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=urllib.error.URLError('refused')):
            with override_settings(TOOLS_AI_MODEL='qwen3.5:9b'):
                h = ai_service.health_check()
        self.assertFalse(h['reachable'])
        self.assertTrue(h['error'])

    @AI_ON
    def test_self_test_ok(self):
        resp = fake_response({'message': {'content': 'OK'}})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=resp):
            ok, detail = ai_service.self_test()
        self.assertTrue(ok)
        self.assertIn('qwen3.5:9b', detail)

    @AI_ON
    def test_self_test_reports_model_not_found(self):
        import io
        import urllib.error
        err = urllib.error.HTTPError(
            'http://x/api/chat', 404, 'Not Found', {},
            io.BytesIO(json.dumps({'error': "model 'qwen3.5:9b' not found"}).encode()))
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=err):
            ok, detail = ai_service.self_test()
        self.assertFalse(ok)
        self.assertIn('404', detail)
        self.assertIn('not pulled', detail)

    @AI_ON
    def test_self_test_reports_unreachable(self):
        import urllib.error
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=urllib.error.URLError('Connection refused')):
            ok, detail = ai_service.self_test()
        self.assertFalse(ok)
        self.assertIn('Cannot reach Ollama', detail)

    def test_self_test_disabled_when_no_model(self):
        # No TOOLS_AI_MODEL and no DB row → AI disabled, clear message, no call.
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen') as urlopen:
            ok, detail = ai_service.self_test()
        self.assertFalse(ok)
        urlopen.assert_not_called()


class ValidatorRetryTests(SimpleTestCase):
    @AI_ON
    def test_unacceptable_first_answer_triggers_strict_retry(self):
        prose = fake_stream({'message': {'content': 'I cannot help with that.'},
                             'done': True})
        strict = fake_stream({'message': {'content': '{"narrative": "ok"}'},
                              'done': True})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=[prose, strict]) as urlopen:
            content = ai_service.generate_json(
                'sys', 'user', is_acceptable=lambda c: c.strip().startswith('{'))
        self.assertEqual(content, '{"narrative": "ok"}')
        self.assertEqual(urlopen.call_count, 2)

    @AI_ON
    def test_acceptable_first_answer_skips_retry(self):
        stream = fake_stream({'message': {'content': '{"narrative": "first"}'},
                              'done': True})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=stream) as urlopen:
            content = ai_service.generate_json(
                'sys', 'user', is_acceptable=lambda c: True)
        self.assertEqual(content, '{"narrative": "first"}')
        self.assertEqual(urlopen.call_count, 1)


class JsonExtractionTests(SimpleTestCase):
    def test_prose_wrapped_json_is_extracted(self):
        raw = ('Sure! Here is the requested analysis:\n'
               '{"narrative": "A logistics system.", "business_domains": ["Logistics"],'
               ' "priority_hint": "Start small."}\nHope this helps!')
        result = _validated(raw)
        self.assertEqual(result['narrative'], 'A logistics system.')

    def test_fenced_json_is_extracted(self):
        raw = '```json\n{"narrative": "Fenced."}\n```'
        result = _validated(raw)
        self.assertEqual(result['narrative'], 'Fenced.')

    def test_pure_prose_still_rejected(self):
        self.assertIsNone(_validated('No JSON here at all.'))


class PayloadTests(SimpleTestCase):
    def test_payload_contains_only_analysis_derived_data(self):
        payload = build_payload(ANALYSIS, SCORING, META, 'ar')
        self.assertEqual(payload['language'], 'Arabic')
        self.assertEqual(payload['score'], 100)
        self.assertEqual(payload['findings'][0]['code'], 'custom_studio_models')
        self.assertEqual(len(payload['most_customized_models']), 12)  # capped
        self.assertIn('Boss Cargo Insurance Wizard', payload['non_standard_modules'])
        self.assertEqual(
            set(payload),
            {'language', 'odoo_version', 'edition', 'score', 'effort_estimate',
             'totals', 'findings', 'most_customized_models', 'non_standard_modules'})

    def test_payload_without_modules_or_meta(self):
        analysis = dict(ANALYSIS, module_summary=None)
        payload = build_payload(analysis, {}, {}, 'xx')
        self.assertEqual(payload['language'], 'English')  # unknown -> English
        self.assertEqual(payload['non_standard_modules'], [])
        self.assertEqual(payload['odoo_version'], 'unknown')


class ValidationTests(SimpleTestCase):
    def test_valid_output_is_capped_and_kept(self):
        raw = json.dumps({
            'narrative': 'n' * 2000,
            'business_domains': ['Logistics', '', 'Insurance', 'Barcode', 'Fifth', 'Sixth'],
            'priority_hint': 'h' * 500,
            'board_summary': 'b' * 1000,
            'questions_for_your_team': ['q' * 400, 'one', '', 'two', 'three', 'four'],
            'extra_key': 'dropped',
        })
        result = _validated(raw)
        self.assertEqual(len(result['narrative']), 1200)
        self.assertEqual(result['business_domains'],
                         ['Logistics', 'Insurance', 'Barcode', 'Fifth'])
        self.assertEqual(len(result['priority_hint']), 300)
        self.assertEqual(len(result['board_summary']), 700)
        questions = result['questions_for_your_team']
        self.assertEqual(len(questions), 4)
        self.assertEqual(len(questions[0]), 220)
        self.assertEqual(questions[1:], ['one', 'two', 'three'])
        self.assertEqual(set(result), {'narrative', 'business_domains', 'priority_hint',
                                       'board_summary', 'questions_for_your_team'})

    def test_new_fields_optional_with_safe_defaults(self):
        result = _validated(json.dumps({'narrative': 'Just a narrative.'}))
        self.assertEqual(result['board_summary'], '')
        self.assertEqual(result['questions_for_your_team'], [])

    def test_garbage_rejected(self):
        self.assertIsNone(_validated('not json'))
        self.assertIsNone(_validated('[]'))
        self.assertIsNone(_validated(json.dumps({'business_domains': ['x']})))  # no narrative
        self.assertIsNone(_validated(json.dumps({'narrative': '   '})))


class GenerateInsightsTests(SimpleTestCase):
    def test_disabled_returns_none(self):
        self.assertIsNone(generate_insights(ANALYSIS, SCORING, META, 'en'))

    @AI_ON
    def test_happy_path_attaches_language(self):
        raw = json.dumps({'narrative': 'A freight operation built in Studio.',
                          'business_domains': ['Logistics'], 'priority_hint': 'Start with waybills.'})
        with mock.patch('tool_studio_xray.insights.ai_service.generate_json',
                        return_value=raw) as gen:
            insights = generate_insights(ANALYSIS, SCORING, META, 'ar')
        self.assertEqual(insights['language'], 'ar')
        self.assertEqual(insights['business_domains'], ['Logistics'])
        # the skill file rode along as the system prompt
        self.assertIn('Hard rules', gen.call_args[0][0])

    @AI_ON
    def test_model_failure_returns_none(self):
        with mock.patch('tool_studio_xray.insights.ai_service.generate_json',
                        return_value=None):
            self.assertIsNone(generate_insights(ANALYSIS, SCORING, META, 'en'))


@override_settings(ALLOWED_HOSTS=['testserver'])
class ProgressAiStepTests(TestCase):
    def _pending_run(self):
        from tools_core.models import ToolRun
        return ToolRun.objects.create(tool_slug='studio_xray', status='pending',
                                      odoo_url='https://x.odoo.com', odoo_db='x')

    @AI_ON
    def test_ai_step_shown_when_enabled(self):
        run = self._pending_run()
        resp = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/')
        content = resp.content.decode()
        self.assertIn('Consulting the AI analyst', content)
        self.assertIn('xray-think-dot', content)
        self.assertIn('const AI_ENABLED = true', content)

    def test_ai_step_hidden_when_disabled(self):
        run = self._pending_run()
        resp = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/')
        content = resp.content.decode()
        self.assertNotIn('Consulting the AI analyst', content)
        self.assertIn('const AI_ENABLED = false', content)

    def test_status_endpoint_maps_ai_step(self):
        run = self._pending_run()
        run.status = 'ai_insights'
        run.save(update_fields=['status'])
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data, {'status': 'ai_insights', 'step': 3, 'error': '',
                                'ai_note': ''})


@override_settings(ALLOWED_HOSTS=['testserver'])
class ReportAiCardTests(TestCase):
    def test_card_rendered_when_insights_present(self):
        run = make_done_run()
        run.result_json['ai_insights'] = {
            'narrative': 'A freight-forwarding operation lives inside Studio.',
            'business_domains': ['Freight & logistics'],
            'priority_hint': 'Start with the waybill models.', 'language': 'en'}
        run.save(update_fields=['result_json'])
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        content = resp.content.decode()
        self.assertIn('AI analyst notes', content)
        self.assertIn('freight-forwarding operation', content)
        self.assertIn('Freight &amp; logistics', content)
        self.assertIn('Where to start:', content)
        self.assertIn('deterministic scan', content)

    def test_board_summary_and_questions_render(self):
        run = make_done_run()
        run.result_json['ai_insights'] = {
            'narrative': 'Narrative.', 'business_domains': [],
            'priority_hint': '', 'language': 'en',
            'board_summary': 'Your daily operations rely on undocumented tools.',
            'questions_for_your_team': ['Who maintains the custom models today?',
                                        'Is there documentation?']}
        run.save(update_fields=['result_json'])
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        content = resp.content.decode()
        self.assertIn('Board-level summary', content)
        self.assertIn('undocumented tools', content)
        self.assertIn('Questions to bring to your team', content)
        self.assertIn('Who maintains the custom models today?', content)

    def test_sections_hidden_without_new_fields(self):
        run = make_done_run()
        run.result_json['ai_insights'] = {
            'narrative': 'Narrative only.', 'business_domains': [],
            'priority_hint': '', 'language': 'en'}
        run.save(update_fields=['result_json'])
        content = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertNotIn('Board-level summary', content)
        self.assertNotIn('Questions to bring to your team', content)

    def test_card_hidden_for_old_payloads(self):
        run = make_done_run()  # no ai_insights key
        resp = self.client.get(f'/en/tools/studio-xray/report/{run.pk}/')
        self.assertNotIn('AI analyst notes', resp.content.decode())


@override_settings(ALLOWED_HOSTS=['testserver'], TOOLS_AI_MODEL='qwen3.5:9b',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PersonalizedEmailTests(TestCase):
    def test_board_summary_lands_in_the_report_email(self):
        import json as json_mod
        from pathlib import Path
        from django.core import mail
        from tool_studio_xray.tasks import run_studio_xray
        from tools_core.connectors import ConnectionInfo
        from tools_core.models import Lead, ToolRun

        inventory = json_mod.load(
            open(Path(__file__).parent / 'fixtures' / 'heavy_studio.json'))
        lead = Lead.objects.create(email='cto@example.com', source_tool='studio_xray')
        run = ToolRun.objects.create(lead=lead, tool_slug='studio_xray',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        insights = {'narrative': 'n', 'business_domains': [], 'priority_hint': '',
                    'board_summary': 'Core operations depend on undocumented Studio tools.',
                    'questions_for_your_team': [], 'language': 'en'}
        with mock.patch('tool_studio_xray.tasks.OdooXmlRpcConnector') as cls, \
                mock.patch('tool_studio_xray.tasks.collect', return_value=inventory), \
                mock.patch('tool_studio_xray.tasks.generate_insights', return_value=insights):
            cls.return_value.test_connection.return_value = \
                ConnectionInfo('17.0', 'enterprise', 'Audit', 'example')
            run_studio_xray(str(run.pk), 'https://x.odoo.com', 'x', 'l', 'k')
        message = next(m for m in mail.outbox if m.to == ['cto@example.com'])
        self.assertIn('Core operations depend on undocumented Studio tools.',
                      message.body)
        html_body = message.alternatives[0][0]
        self.assertIn('Core operations depend on undocumented Studio tools.', html_body)


@override_settings(ALLOWED_HOSTS=['testserver'], TOOLS_AI_MODEL='qwen3.5:9b',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TaskAiIntegrationTests(TestCase):
    def test_task_stores_insights_and_survives_ai_failure(self):
        import json as json_mod
        from pathlib import Path
        from tool_studio_xray.tasks import run_studio_xray
        from tools_core.connectors import ConnectionInfo
        from tools_core.models import ToolRun

        fixtures = Path(__file__).parent / 'fixtures' / 'heavy_studio.json'
        inventory = json_mod.load(open(fixtures))
        info = ConnectionInfo('17.0', 'enterprise', 'Audit', 'example')

        for ai_result in ({'narrative': 'n', 'business_domains': [],
                           'priority_hint': '', 'language': 'ar'}, None):
            run = ToolRun.objects.create(tool_slug='studio_xray',
                                         odoo_url='https://x.odoo.com', odoo_db='x')
            with mock.patch('tool_studio_xray.tasks.OdooXmlRpcConnector') as cls, \
                    mock.patch('tool_studio_xray.tasks.collect', return_value=inventory), \
                    mock.patch('tool_studio_xray.tasks.generate_insights',
                               return_value=ai_result) as gen:
                cls.return_value.test_connection.return_value = info
                run_studio_xray(str(run.pk), 'https://x.odoo.com', 'x', 'l', 'k', 'ar')
            run.refresh_from_db()
            self.assertEqual(run.status, 'done')
            self.assertEqual(run.result_json['ai_insights'], ai_result)
            # the AI can never touch the deterministic results
            self.assertEqual(run.result_json['scoring']['score'], 100)
            self.assertEqual(run.result_json['scoring']['effort_estimate'], '4+ weeks')
            self.assertTrue(run.result_json['analysis']['findings'])
            gen.assert_called_once()
            self.assertEqual(gen.call_args[0][3], 'ar')  # language forwarded


LOCMEM_TOOLS_CACHE = override_settings(CACHES={
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    'tools': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
              'LOCATION': 'tools-test'},
})


@LOCMEM_TOOLS_CACHE
class LiveThinkingNoteTests(TestCase):
    def test_note_roundtrip_and_clear(self):
        from tools_core.utils import clear_run_note, get_run_note, set_run_note
        set_run_note('abc', 'reasoning tail')
        self.assertEqual(get_run_note('abc'), 'reasoning tail')
        clear_run_note('abc')
        self.assertEqual(get_run_note('abc'), '')

    @override_settings(ALLOWED_HOSTS=['testserver'])
    def test_status_endpoint_serves_live_note(self):
        from tools_core.models import ToolRun
        from tools_core.utils import set_run_note
        run = ToolRun.objects.create(tool_slug='studio_xray', status='ai_insights',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        set_run_note(run.pk, 'The x_ models look like freight documents')
        data = self.client.get(f'/en/tools/studio-xray/run/{run.pk}/status/').json()
        self.assertEqual(data['ai_note'], 'The x_ models look like freight documents')

    def test_task_note_writer_collapses_and_caps(self):
        from tool_studio_xray.tasks import _thinking_note_writer
        from tools_core.utils import get_run_note
        write = _thinking_note_writer('runx')
        write('line one\n\n   line two   ' + 'y' * 400)
        note = get_run_note('runx')
        self.assertLessEqual(len(note), 220)
        self.assertNotIn('\n', note)


class ThinkTagStrippingTests(SimpleTestCase):
    def test_inline_think_tags_are_removed_before_parsing(self):
        raw = '<think>step by step reasoning…</think>{"narrative": "Clean output."}'
        result = _validated(raw)
        self.assertEqual(result['narrative'], 'Clean output.')


class RetryReserveTests(SimpleTestCase):
    @AI_ON
    @override_settings(TOOLS_AI_TIMEOUT=200, TOOLS_AI_THINKING_BUDGET=10000)
    def test_first_attempt_stops_early_to_guarantee_retry_room(self):
        from tools_core.services.ai_service import RETRY_RESERVE
        with mock.patch('tools_core.services.ai_service._attempt',
                        side_effect=[(None, True), ('{"narrative": "ok"}', False)]) as attempt:
            content = ai_service.generate_json('sys', 'user')
        self.assertEqual(content, '{"narrative": "ok"}')
        first_deadline = attempt.call_args_list[0][0][1]
        retry_deadline = attempt.call_args_list[1][0][1]
        self.assertAlmostEqual(retry_deadline - first_deadline, RETRY_RESERVE, delta=0.5)

    @AI_ON
    @override_settings(TOOLS_AI_TIMEOUT=60, TOOLS_AI_THINKING_BUDGET=10000)
    def test_tiny_budget_skips_the_reserve(self):
        # 60s budget is below 2x reserve: attempt 1 keeps the full deadline
        with mock.patch('tools_core.services.ai_service._attempt',
                        side_effect=[(None, True), (None, False)]) as attempt:
            ai_service.generate_json('sys', 'user')
        first_deadline = attempt.call_args_list[0][0][1]
        retry_deadline = attempt.call_args_list[1][0][1]
        self.assertAlmostEqual(retry_deadline, first_deadline, delta=0.5)

    @AI_ON
    @override_settings(TOOLS_AI_TIMEOUT=500, TOOLS_AI_THINKING_BUDGET=50)
    def test_thinking_budget_caps_the_first_attempt(self):
        with mock.patch('tools_core.services.ai_service._attempt',
                        side_effect=[(None, True), ('{"narrative": "x"}', False)]) as attempt:
            ai_service.generate_json('sys', 'user')
        first_deadline = attempt.call_args_list[0][0][1]
        retry_deadline = attempt.call_args_list[1][0][1]
        # the showtime cut at ~50s, while the strict answer kept ~500s
        self.assertAlmostEqual(retry_deadline - first_deadline, 450, delta=1)


class ThinkingBudgetZeroTests(SimpleTestCase):
    @AI_ON
    @override_settings(TOOLS_AI_THINKING_BUDGET=0)
    def test_zero_budget_goes_straight_to_strict_mode(self):
        strict = fake_stream({'message': {'content': '{"narrative": "fast"}'},
                              'done': True})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        return_value=strict) as urlopen:
            content = ai_service.generate_json('sys', 'user')
        self.assertEqual(content, '{"narrative": "fast"}')
        self.assertEqual(urlopen.call_count, 1)
        body = json.loads(urlopen.call_args[0][0].data.decode())
        self.assertEqual(body['format'], 'json')
        self.assertIs(body['think'], False)

    @AI_ON
    @override_settings(TOOLS_AI_THINKING_BUDGET=0)
    def test_think_param_rejection_falls_back_without_it(self):
        # non-thinking models can reject think=false with an HTTP error
        ok = fake_stream({'message': {'content': '{"narrative": "np"}'}, 'done': True})
        with mock.patch('tools_core.services.ai_service.urllib.request.urlopen',
                        side_effect=[OSError('400: think unsupported'), ok]) as urlopen:
            content = ai_service.generate_json('sys', 'user')
        self.assertEqual(content, '{"narrative": "np"}')
        self.assertEqual(urlopen.call_count, 2)
        second = json.loads(urlopen.call_args_list[1][0][0].data.decode())
        self.assertNotIn('think', second)
        self.assertEqual(second['format'], 'json')


@override_settings(ALLOWED_HOSTS=['testserver'], TOOLS_AI_MODEL='qwen3.5:9b',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SoftTimeoutDuringAiTests(TestCase):
    def test_soft_timeout_in_ai_phase_ships_report_without_card(self):
        import json as json_mod
        from pathlib import Path
        from celery.exceptions import SoftTimeLimitExceeded
        from tool_studio_xray.tasks import run_studio_xray
        from tools_core.connectors import ConnectionInfo
        from tools_core.models import ToolRun

        inventory = json_mod.load(
            open(Path(__file__).parent / 'fixtures' / 'heavy_studio.json'))
        run = ToolRun.objects.create(tool_slug='studio_xray',
                                     odoo_url='https://x.odoo.com', odoo_db='x')
        with mock.patch('tool_studio_xray.tasks.OdooXmlRpcConnector') as cls, \
                mock.patch('tool_studio_xray.tasks.collect', return_value=inventory), \
                mock.patch('tool_studio_xray.tasks.generate_insights',
                           side_effect=SoftTimeLimitExceeded()):
            cls.return_value.test_connection.return_value = \
                ConnectionInfo('17.0', 'enterprise', 'Audit', 'example')
            run_studio_xray(str(run.pk), 'https://x.odoo.com', 'x', 'l', 'k')
        run.refresh_from_db()
        # the deterministic report survived the slow model
        self.assertEqual(run.status, 'done')
        self.assertIsNone(run.result_json['ai_insights'])
        self.assertEqual(run.result_json['scoring']['score'], 100)
