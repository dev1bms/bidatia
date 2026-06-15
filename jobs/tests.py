import uuid

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import BackgroundTask
from .services import create_task, serialize_status


@override_settings(ALLOWED_HOSTS=['testserver'])
class BackgroundTaskModelTests(TestCase):
    def test_create_defaults_to_queued_and_active(self):
        task = create_task(task_type='demo', title='Doing the thing')
        self.assertEqual(task.status, BackgroundTask.STATUS_QUEUED)
        self.assertTrue(task.is_active)
        self.assertIsInstance(task.id, uuid.UUID)

    def test_transitions(self):
        task = create_task(task_type='demo', title='X')
        task.mark_running(message='Step 1', progress=40)
        self.assertEqual(task.status, BackgroundTask.STATUS_RUNNING)
        self.assertEqual(task.progress, 40)
        self.assertIsNotNone(task.started_at)
        task.mark_success(message='Done', result_url='/result/')
        self.assertEqual(task.status, BackgroundTask.STATUS_SUCCESS)
        self.assertEqual(task.progress, 100)
        self.assertFalse(task.is_active)
        self.assertIsNotNone(task.finished_at)

    def test_failure_detail_stays_admin_only(self):
        task = create_task(task_type='demo', title='X')
        task.mark_failed(error_message='Traceback: SMTP password=hunter2 leaked')
        payload = serialize_status(task)
        self.assertEqual(payload['status'], BackgroundTask.STATUS_FAILED)
        self.assertFalse(payload['poll'])
        # The raw error / any secret never reaches the browser payload.
        self.assertNotIn('hunter2', str(payload))
        self.assertNotIn('Traceback', str(payload))
        self.assertTrue(payload['error'])  # a generic, safe message instead


@override_settings(ALLOWED_HOSTS=['testserver'])
class StatusApiTests(TestCase):
    def test_queued_payload_tells_browser_to_poll(self):
        task = create_task(task_type='demo', title='X')
        resp = self.client.get(reverse('jobs:status', args=[task.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'queued')
        self.assertTrue(data['poll'])
        self.assertEqual(resp['Cache-Control'], 'no-store')

    def test_success_payload_has_result_url_and_stops_polling(self):
        task = create_task(task_type='demo', title='X')
        task.mark_success(result_url='/thank-you/')
        data = self.client.get(reverse('jobs:status', args=[task.id])).json()
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['poll'])
        self.assertEqual(data['result_url'], '/thank-you/')

    def test_unknown_task_is_404(self):
        resp = self.client.get(reverse('jobs:status', args=[uuid.uuid4()]))
        self.assertEqual(resp.status_code, 404)

    def test_owned_task_hidden_from_other_session(self):
        task = create_task(task_type='demo', title='X', session_key='not-your-session')
        resp = self.client.get(reverse('jobs:status', args=[task.id]))
        self.assertEqual(resp.status_code, 404)

    def test_status_page_renders_component(self):
        task = create_task(task_type='demo', title='Your request')
        resp = self.client.get(reverse('jobs:detail', args=[task.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'js-task-status')


@override_settings(ALLOWED_HOSTS=['testserver'])
class ContactBackgroundFlowTests(TestCase):
    def test_contact_post_queues_task_sends_email_and_shows_status(self):
        resp = self.client.post(
            reverse('leads:contact'),
            {'name': 'Ada', 'email': 'ada@example.com', 'message': 'Hello'},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(reverse('leads:contact_success'),
                      [url for url, _code in resp.redirect_chain])
        # The browser gets the reusable status component on the success page.
        self.assertContains(resp, 'js-task-status')
        # A trackable task was created and (eager mode) completed; email delivered.
        task = BackgroundTask.objects.filter(task_type='contact_email').first()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, BackgroundTask.STATUS_SUCCESS)
        self.assertEqual(len(mail.outbox), 1)

    def test_contact_post_does_not_block_on_missing_broker(self):
        # Even if dispatch fell back to inline, the response is a fast redirect.
        resp = self.client.post(
            reverse('leads:contact'),
            {'name': 'Grace', 'email': 'grace@example.com', 'message': 'Hi'},
        )
        self.assertEqual(resp.status_code, 302)
