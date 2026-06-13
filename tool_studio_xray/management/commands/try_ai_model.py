"""Benchmark an Ollama model against the real Studio X-Ray skill + payload.

Run ON THE SERVER (where Ollama lives):

    python manage.py try_ai_model gemma4:26b --language ar
    python manage.py try_ai_model command-r7b-arabic:latest --language ar

Uses the heavy test fixture as a realistic scan, so candidates can be
compared on exactly the production prompt: validity, quality and speed.
Nothing is stored; settings are only overridden for this process.
"""
import json
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from tool_studio_xray.analyzer import analyze
from tool_studio_xray.insights import generate_insights
from tool_studio_xray.scoring import compute_score

FIXTURE = Path(__file__).resolve().parents[2] / 'tests' / 'fixtures' / 'heavy_studio.json'


class Command(BaseCommand):
    help = 'Try an Ollama model with the real X-Ray insights prompt and report timing/quality.'

    def add_arguments(self, parser):
        parser.add_argument('model', help='Ollama model name, e.g. gemma4:26b')
        parser.add_argument('--language', default='ar', choices=['en', 'es', 'ar'])
        parser.add_argument('--timeout', type=int, default=None,
                            help='Override TOOLS_AI_TIMEOUT for this run')
        parser.add_argument('--thinking-budget', type=int, default=None,
                            help='Override TOOLS_AI_THINKING_BUDGET (0 = strict only)')

    def handle(self, *args, **options):
        settings.TOOLS_AI_MODEL = options['model']
        if options['timeout']:
            settings.TOOLS_AI_TIMEOUT = options['timeout']
        if options['thinking_budget'] is not None:
            settings.TOOLS_AI_THINKING_BUDGET = options['thinking_budget']

        inventory = json.loads(FIXTURE.read_text())
        analysis = analyze(inventory)
        scoring = compute_score(analysis['totals'])

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Model: {options['model']}  ·  language: {options['language']}  ·  "
            f"timeout: {settings.TOOLS_AI_TIMEOUT}s  ·  "
            f"thinking budget: {settings.TOOLS_AI_THINKING_BUDGET}s"))

        thinking_chars = {'n': 0}

        def on_thinking(text):
            thinking_chars['n'] = len(text)
            self.stdout.write(f'\r  thinking… {len(text)} chars', ending='')
            self.stdout.flush()

        started = time.monotonic()
        insights = generate_insights(
            analysis, scoring, inventory.get('meta', {}),
            options['language'], on_thinking=on_thinking)
        elapsed = time.monotonic() - started

        self.stdout.write('')  # newline after the \r updates
        self.stdout.write(f'  elapsed: {elapsed:.1f}s  ·  thinking trace: {thinking_chars["n"]} chars')

        if not insights:
            self.stdout.write(self.style.ERROR(
                '  RESULT: no valid insights (see WARNING lines above for the reason)'))
            return

        self.stdout.write(self.style.SUCCESS('  RESULT: valid insights'))
        self.stdout.write(json.dumps(insights, ensure_ascii=False, indent=2))
