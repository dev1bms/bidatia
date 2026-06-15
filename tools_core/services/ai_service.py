"""Local-AI helper: talks to an Ollama instance on (or near) this server.

Design rules, shared by every tool that uses it:
- The model INTERPRETS finished, deterministic results. It never decides
  scores, severities or counts.
- Callers must never include credentials in prompts (the services that build
  payloads only ever see analysis output, which contains none).
- Everything stays local: the default OLLAMA_URL is loopback, so client
  metadata is never sent to a third-party AI provider.
- Best-effort: any failure (Ollama down, deadline, bad output) returns None —
  a report must always be able to ship without the AI section.

The request STREAMS. Two reasons:
1. qwen3.x are thinking models — streaming lets us enforce one overall
   deadline (TOOLS_AI_TIMEOUT) instead of a blind blocking read.
2. The accumulated `thinking` trace is forwarded to an optional callback so
   the progress page can show the model's actual reasoning live.
"""
import json
import logging
import time
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger('bidatia.tools')

# Keep the model warm between scans without pinning RAM forever.
KEEP_ALIVE = '10m'

# Per-read socket timeout (inactivity); the overall budget is TOOLS_AI_TIMEOUT.
READ_TIMEOUT = 30

GENERATION_OPTIONS = {
    'temperature': 0.2,    # interpretation, not creativity
    'num_ctx': 4096,       # payloads are small summaries by design
    # THINKING TOKENS COUNT TOWARD THIS BUDGET on reasoning models — too low
    # and the model exhausts it mid-reasoning, returning EMPTY content.
    'num_predict': 4096,
}

# Retry without thinking only if at least this much of the budget remains.
MIN_RETRY_BUDGET = 30

# Attempt 1 (with thinking) stops this many seconds before the overall
# deadline, so the fast no-thinking retry ALWAYS has room to produce the
# answer even when reasoning runs long.
RETRY_RESERVE = 45

# Forward thinking to the callback at most this often.
THINKING_CALLBACK_INTERVAL = 1.0


def is_enabled():
    # Admin-managed AI Settings (site_config) decide this at runtime, falling
    # back to the TOOLS_AI_MODEL environment value when no row is configured.
    from site_config import services as config
    return bool(config.ai_settings()['enabled'])


def generate_json(system_prompt, user_prompt, on_thinking=None, is_acceptable=None,
                  allow_thinking=True):
    """One streamed chat completion expected to yield JSON.

    Returns the raw content string (callers parse/validate) or None on any
    failure. `on_thinking(text_so_far)` — when given — receives the growing
    reasoning trace of thinking models, throttled to ~1/s. `is_acceptable`
    lets the caller validate the first answer before it is accepted.
    `allow_thinking=False` skips the free-form reasoning attempt entirely —
    for interactive callers (report chat) where latency matters most.

    Attempt strategy (qwen3.x + Ollama specifics, confirmed in production):
    1. WITH thinking, WITHOUT format=json — the grammar constraint combined
       with thinking reliably ends generations with EMPTY content, so the
       first attempt lets the model answer freely after reasoning (callers
       extract the JSON).
    2. If the answer is empty or rejected by `is_acceptable`, retry with
       thinking DISABLED and format=json forced — fast and strict.
    """
    from site_config import services as config
    ai = config.ai_settings()
    if not ai['enabled']:
        return None

    # Optional admin-managed "skills" prepended to the caller's system prompt.
    if ai.get('system_instructions'):
        system_prompt = f"{ai['system_instructions']}\n\n{system_prompt}"

    # Admin-tunable options override the defaults (temperature / output cap).
    options = dict(GENERATION_OPTIONS)
    if ai.get('temperature') is not None:
        options['temperature'] = float(ai['temperature'])
    if ai.get('max_output_tokens'):
        options['num_predict'] = int(ai['max_output_tokens'])

    base_body = {
        'model': ai['model'],
        'stream': True,
        'keep_alive': KEEP_ALIVE,
        'options': options,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
    }
    timeout = int(ai['timeout'])
    deadline = time.monotonic() + timeout
    thinking_budget = max(int(ai['thinking_budget'] or 0), 0)

    saw_thinking = False
    if thinking_budget > 0 and allow_thinking:
        # Free-form attempt: real reasoning streams to the progress page for
        # up to TOOLS_AI_THINKING_BUDGET seconds, then we cut to strict mode.
        first_deadline = deadline
        if timeout > 2 * RETRY_RESERVE:
            first_deadline = deadline - RETRY_RESERVE
        first_deadline = min(first_deadline, time.monotonic() + thinking_budget)

        content, saw_thinking = _attempt(dict(base_body), first_deadline, on_thinking)
        if content and (is_acceptable is None or is_acceptable(content)):
            return content
        if content:
            logger.warning('ai_service: first answer failed validation')
        if time.monotonic() > deadline - MIN_RETRY_BUDGET:
            return None
        logger.warning('ai_service: retrying in strict JSON mode')

    strict_body = dict(base_body)
    strict_body['format'] = 'json'
    strict_body['think'] = False
    content, _ = _attempt(strict_body, deadline, None)
    if content:
        return content

    # Some non-thinking models reject the think parameter outright. When the
    # model never demonstrated thinking, give strict mode one more try
    # without it.
    if saw_thinking or time.monotonic() > deadline - MIN_RETRY_BUDGET:
        return None
    fallback_body = dict(base_body)
    fallback_body['format'] = 'json'
    content, _ = _attempt(fallback_body, deadline, None)
    return content


def _attempt(body, deadline, on_thinking):
    """Returns (content, saw_thinking)."""
    request = urllib.request.Request(
        settings.OLLAMA_URL.rstrip('/') + '/api/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    content_parts, thinking_parts = [], []
    last_callback = 0.0

    try:
        with urllib.request.urlopen(request, timeout=READ_TIMEOUT) as response:
            for raw_line in response:
                if time.monotonic() > deadline:
                    logger.warning(
                        'ai_service: attempt budget exceeded mid-generation '
                        '(tune TOOLS_AI_TIMEOUT / TOOLS_AI_THINKING_BUDGET)')
                    return None, bool(thinking_parts)
                line = raw_line.strip()
                if not line:
                    continue
                chunk = json.loads(line)
                message = chunk.get('message') or {}
                if message.get('thinking'):
                    thinking_parts.append(message['thinking'])
                if message.get('content'):
                    content_parts.append(message['content'])
                if (on_thinking and thinking_parts
                        and time.monotonic() - last_callback > THINKING_CALLBACK_INTERVAL):
                    on_thinking(''.join(thinking_parts))
                    last_callback = time.monotonic()
                if chunk.get('done'):
                    break
    except Exception as exc:  # noqa: BLE001 — AI is always best-effort
        # Type only: no prompt contents, no payloads.
        logger.warning('ai_service: generation failed (%s)', type(exc).__name__)
        return None, bool(thinking_parts)

    content = ''.join(content_parts).strip()
    if not content:
        logger.warning('ai_service: model returned empty content '
                       '(thinking may have consumed the token budget)')
        return None, bool(thinking_parts)
    return content, bool(thinking_parts)


# ── Admin diagnostics: discover models, check health, run a live self-test ────
def list_models(timeout=4):
    """Names of the models actually pulled on the Ollama host (``/api/tags``).
    Raises on any connection/HTTP error so callers can report it."""
    url = settings.OLLAMA_URL.rstrip('/') + '/api/tags'
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = json.loads(response.read().decode('utf-8'))
    return sorted(m['name'] for m in data.get('models', []) if m.get('name'))


def health_check(timeout=4):
    """A snapshot for the admin: is Ollama reachable, which models are pulled,
    and is the configured model among them. Never raises."""
    from site_config import services as config

    ai = config.ai_settings()
    info = {
        'enabled': ai['enabled'],
        'model': ai['model'],
        'url': settings.OLLAMA_URL,
        'reachable': False,
        'models': [],
        'model_present': False,
        'error': '',
    }
    if not ai['model']:
        info['error'] = 'no_model_configured'
        return info
    try:
        info['models'] = list_models(timeout=timeout)
        info['reachable'] = True
        info['model_present'] = ai['model'] in info['models']
    except urllib.error.URLError as exc:
        info['error'] = f'unreachable: {getattr(exc, "reason", exc)}'
    except Exception as exc:  # noqa: BLE001
        info['error'] = type(exc).__name__
    return info


def self_test():
    """Make one tiny real generation with the configured model. Returns
    (ok: bool, detail: str) with a precise, secret-free reason on failure —
    e.g. 'HTTP 404: model not found' or 'cannot reach Ollama'."""
    from site_config import services as config

    ai = config.ai_settings()
    if not ai['enabled']:
        return False, 'AI is disabled (Enabled is off, or no model configured).'
    if not ai['model']:
        return False, 'No model configured — set Model name or TOOLS_AI_MODEL.'

    body = {
        'model': ai['model'], 'stream': False, 'keep_alive': KEEP_ALIVE,
        'messages': [{'role': 'user', 'content': 'Reply with the single word: OK'}],
        'options': {'num_predict': 16, 'temperature': 0},
    }
    request = urllib.request.Request(
        settings.OLLAMA_URL.rstrip('/') + '/api/chat',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    started = time.monotonic()
    try:
        # Generous cap: a cold model load can take a while on first call.
        with urllib.request.urlopen(request, timeout=min(int(ai['timeout']), 180)) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = json.loads(exc.read().decode('utf-8')).get('error', '')
        except Exception:  # noqa: BLE001
            pass
        hint = (f" — model '{ai['model']}' is not pulled on this server"
                if exc.code == 404 else '')
        return False, f'Ollama returned HTTP {exc.code}: {detail or exc.reason}{hint}'
    except urllib.error.URLError as exc:
        return False, (f"Cannot reach Ollama at {settings.OLLAMA_URL} "
                       f"({getattr(exc, 'reason', exc)}). Is the service running?")
    except Exception as exc:  # noqa: BLE001
        return False, f'{type(exc).__name__}: {exc}'[:200]

    text = ((data.get('message') or {}).get('content') or '').strip()
    elapsed = time.monotonic() - started
    if text:
        return True, f"OK — '{ai['model']}' replied in {elapsed:.1f}s."
    return False, f"'{ai['model']}' connected but returned empty content."
