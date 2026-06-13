import json
import re
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from tool_studio_xray.chat import _validated_answer, build_chat_payload
from tool_studio_xray.tests.test_views import make_done_run
from tools_core.models import ReportQuestion

AI_ON = override_settings(TOOLS_AI_MODEL='gemma4:26b')
DELAY = 'tool_studio_xray.views.answer_report_question.delay'


def ask_url(run):
    return f'/en/tools/studio-xray/report/{run.pk}/ask/'


class ChatPayloadTests(SimpleTestCase):
    def test_payload_is_grounded_and_capped(self):
        payload = build_chat_payload(
            {'analysis': {'totals': {'custom_models': 2},
                          'findings': [{'code': 'x', 'severity': 'info', 'count': 1,
                                        'examples': ['a'] * 20}],
                          'model_breakdown': []},
             'scoring': {'score': 37, 'effort_estimate': '4–8 days'},
             'meta': {'server_version': '17.0', 'edition': 'enterprise'}},
            'q' * 1000, 'ar',
            history=[('old q %d' % i, 'old a %d' % i) for i in range(10)])
        self.assertEqual(payload['language'], 'Arabic')
        self.assertEqual(len(payload['question']), 300)          # capped
        self.assertEqual(len(payload['recent_conversation']), 3)  # last 3 only
        self.assertEqual(len(payload['report']['findings'][0]['examples']), 5)
        self.assertEqual(payload['report']['score'], 37)

    def test_answer_validation(self):
        self.assertEqual(_validated_answer('{"answer": "Fine."}'), 'Fine.')
        self.assertEqual(len(_validated_answer(json.dumps({'answer': 'a' * 5000}))), 1000)
        self.assertIsNone(_validated_answer('not json'))
        self.assertIsNone(_validated_answer('{"answer": "  "}'))
        self.assertIsNone(_validated_answer('{"other": "x"}'))


@override_settings(ALLOWED_HOSTS=['testserver'])
@AI_ON
class AskQuestionViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def _ask(self, run, text='What is the most urgent risk?'):
        return self.client.post(ask_url(run), json.dumps({'question': text}),
                                content_type='application/json')

    def test_question_created_and_queued(self):
        run = make_done_run()
        with mock.patch(DELAY) as delay:
            data = self._ask(run).json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['remaining'], 9)
        question = ReportQuestion.objects.get()
        self.assertEqual(question.run, run)
        self.assertEqual(question.language, 'en')
        delay.assert_called_once_with(str(question.pk))

    def test_unavailable_when_ai_disabled(self):
        run = make_done_run()
        with override_settings(TOOLS_AI_MODEL=''):
            resp = self._ask(run)
        self.assertEqual(resp.status_code, 409)

    def test_unavailable_for_wiped_report(self):
        run = make_done_run(result_json=None)
        self.assertEqual(self._ask(run).status_code, 409)

    def test_question_length_validated(self):
        run = make_done_run()
        with mock.patch(DELAY):
            self.assertEqual(self._ask(run, 'ab').status_code, 400)
            self.assertEqual(self._ask(run, 'x' * 301).status_code, 400)
        self.assertEqual(ReportQuestion.objects.count(), 0)

    def test_per_run_limit(self):
        run = make_done_run()
        for i in range(10):
            ReportQuestion.objects.create(run=run, question='q%d' % i)
        resp = self._ask(run)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.json()['code'], 'limit')

    def test_broker_down_marks_question_failed(self):
        run = make_done_run()
        with mock.patch(DELAY, side_effect=OSError('down')):
            data = self._ask(run).json()
        self.assertTrue(data['ok'])
        self.assertEqual(ReportQuestion.objects.get().status, 'failed')

    def test_status_endpoint(self):
        run = make_done_run()
        question = ReportQuestion.objects.create(
            run=run, question='q', answer='The answer.', status='done')
        data = self.client.get(
            f'/en/tools/studio-xray/question/{question.pk}/').json()
        self.assertEqual(data, {'status': 'done', 'answer': 'The answer.'})


@override_settings(ALLOWED_HOSTS=['testserver'])
@AI_ON
class AnswerTaskTests(TestCase):
    def test_success_path_with_history(self):
        from tool_studio_xray.tasks import answer_report_question
        run = make_done_run()
        ReportQuestion.objects.create(run=run, question='earlier?',
                                      answer='earlier answer', status='done')
        question = ReportQuestion.objects.create(run=run, question='And now?',
                                                 language='ar')
        with mock.patch('tool_studio_xray.chat.ai_service.generate_json',
                        return_value='{"answer": "Grounded reply."}') as gen:
            answer_report_question(str(question.pk))
        question.refresh_from_db()
        self.assertEqual(question.status, 'done')
        self.assertEqual(question.answer, 'Grounded reply.')
        # strict (no thinking) + history rode along
        self.assertFalse(gen.call_args.kwargs['allow_thinking'])
        sent = json.loads(gen.call_args[0][1])
        self.assertEqual(sent['recent_conversation'][0]['question'], 'earlier?')
        self.assertEqual(sent['question'], 'And now?')

    def test_model_failure_marks_failed(self):
        from tool_studio_xray.tasks import answer_report_question
        run = make_done_run()
        question = ReportQuestion.objects.create(run=run, question='q?')
        with mock.patch('tool_studio_xray.chat.ai_service.generate_json',
                        return_value=None):
            answer_report_question(str(question.pk))
        question.refresh_from_db()
        self.assertEqual(question.status, 'failed')

    def test_wiped_report_marks_failed_without_calling_model(self):
        from tool_studio_xray.tasks import answer_report_question
        run = make_done_run(result_json=None)
        question = ReportQuestion.objects.create(run=run, question='q?')
        with mock.patch('tool_studio_xray.chat.ai_service.generate_json') as gen:
            answer_report_question(str(question.pk))
        question.refresh_from_db()
        self.assertEqual(question.status, 'failed')
        gen.assert_not_called()


@override_settings(ALLOWED_HOSTS=['testserver'])
class ChatWidgetRenderTests(TestCase):
    @AI_ON
    def test_widget_rendered_with_starters(self):
        run = make_done_run()
        content = self.client.get(
            f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertIn('Ask the analyst', content)
        self.assertIn('What is the most urgent risk in my system?', content)
        self.assertIn('2 custom models', content)        # tailored starter
        self.assertIn('questions left', content)
        self.assertIn('xrayChat()', content)

    def test_widget_absent_when_ai_disabled(self):
        run = make_done_run()
        content = self.client.get(
            f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertNotIn('Ask the analyst', content)

    @AI_ON
    def test_arabic_page_renders_widget(self):
        run = make_done_run()
        resp = self.client.get(f'/ar/tools/studio-xray/report/{run.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('xrayChat()', resp.content.decode())

    @AI_ON
    def test_history_restored_on_page_load(self):
        run = make_done_run()
        ReportQuestion.objects.create(run=run, question='Earlier question?',
                                      answer='Earlier answer.', status='done')
        pending = ReportQuestion.objects.create(run=run, question='Mid-flight question?')
        ReportQuestion.objects.create(run=run, question='', answer='', status='done')  # wiped
        content = self.client.get(
            f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertIn('Earlier question?', content)
        self.assertIn('Earlier answer.', content)
        self.assertIn('_restoreHistory', content)
        payload = json.loads(re.search(
            r'<script id="xray-chat-history"[^>]*>(.*?)</script>', content, re.S).group(1))
        self.assertEqual(len(payload), 2)                       # wiped row excluded
        self.assertEqual(payload[0]['status'], 'done')
        self.assertEqual(payload[1]['id'], str(pending.pk))     # resume-polling hook
        self.assertEqual(payload[1]['status'], 'pending')

    @AI_ON
    def test_split_panel_controls_rendered(self):
        run = make_done_run()
        content = self.client.get(
            f'/en/tools/studio-xray/report/{run.pk}/').content.decode()
        self.assertIn('cursor-col-resize', content)   # drag divider
        self.assertIn('startResize', content)         # resize wiring
        self.assertIn('xrayChatPanel', content)       # layout persisted in localStorage
        self.assertIn('--xray-chat-w', content)       # split width variable
        self.assertIn('xray-split', content)          # report yields width when docked
        self.assertIn('Hide the chat', content)       # explicit hide control
        self.assertIn('Ask the analyst', content)     # launcher to reopen


class ChatWipeTests(TestCase):
    def test_expired_chat_text_wiped_rows_kept(self):
        from datetime import timedelta
        from django.utils import timezone
        from tools_core.models import ToolRun
        from tools_core.tasks import wipe_expired_tool_results

        run = make_done_run()
        ToolRun.objects.filter(pk=run.pk).update(
            expires_at=timezone.now() - timedelta(hours=1))
        ReportQuestion.objects.create(run=run, question='secret q',
                                      answer='secret a', status='done')
        wipe_expired_tool_results()
        question = ReportQuestion.objects.get()
        self.assertEqual(question.question, '')
        self.assertEqual(question.answer, '')
        self.assertEqual(question.status, 'done')  # row + status survive
