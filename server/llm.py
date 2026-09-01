import logging
import queue
import random
import re
import threading
import time

import requests

import config
import runtime_settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1

HEARTBEAT_INTERVAL_SECONDS = 15

logger = logging.getLogger(__name__)


def build_prompt(
    attachments: dict, date_start: str, date_end: str, prompt_template: str
) -> str:
    """Text-only preview of what gets sent to the LLM (instructions + attachment
    summary), so callers can display it (e.g. as a progress event) without embedding
    image data."""
    prompt = prompt_template.replace("[DATA_INICIAL]", date_start).replace(
        "[DATA_FINAL]", date_end
    )

    summary = "\n".join(
        f"- {filename} ({len(parts)} página(s))"
        for filename, parts in attachments.items()
    )

    return f"{prompt}\n\nARQUIVOS ANEXADOS:\n\n{summary}"


def build_messages(
    attachments: dict, date_start: str, date_end: str, prompt_template: str
) -> list:
    """Assembles the actual multimodal `messages` payload sent to OpenRouter: the
    prompt instructions followed by each file's label and image parts."""
    prompt = prompt_template.replace("[DATA_INICIAL]", date_start).replace(
        "[DATA_FINAL]", date_end
    )

    content = [{"type": "text", "text": prompt}]
    for filename, parts in attachments.items():
        for page_number, part in enumerate(parts, start=1):
            content.append(
                {
                    "type": "text",
                    "text": f"--- Arquivo: {filename} | Página {page_number} ---",
                }
            )
            content.append(part)

    return [{"role": "user", "content": content}]


def structure(
    attachments: dict, date_start: str, date_end: str, prompt_template: str
):
    """Generator: yields {"type": "retry", ...} progress events while a transient
    OpenRouter failure is being retried, then a final
    {"type": "result", "result": (csv_text, notes)} once the model responds."""
    messages = build_messages(attachments, date_start, date_end, prompt_template)

    response = None
    for progress in _post_with_retry(
        {
            "model": runtime_settings.get_active_model(),
            "messages": messages,
        }
    ):
        if progress["type"] == "retry":
            yield progress
        else:
            response = progress["response"]

    content = response.json()["choices"][0]["message"]["content"]
    yield {"type": "result", "result": _split_csv_and_notes(content)}


def structure_with_heartbeat(
    attachments: dict,
    date_start: str,
    date_end: str,
    prompt_template: str,
    interval: float = HEARTBEAT_INTERVAL_SECONDS,
):
    """Same events as `structure`, plus a `{"type": "heartbeat"}` every `interval`
    seconds while the (blocking) OpenRouter call is in flight. A streaming HTTP
    caller turns each heartbeat into a byte on the wire so idle-timeout proxies
    (Cloudflare's 524, nginx `proxy_read_timeout`) don't sever the response while
    the model is still thinking. The real call runs on a daemon thread; if the
    client disconnects it keeps running until `requests` times out, then exits."""
    results: "queue.Queue" = queue.Queue()

    def worker():
        try:
            for progress in structure(
                attachments, date_start, date_end, prompt_template
            ):
                results.put(("item", progress))
        except Exception as exc:  # re-raised on the consumer thread
            results.put(("error", exc))
        finally:
            results.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()

    while True:
        try:
            kind, payload = results.get(timeout=interval)
        except queue.Empty:
            yield {"type": "heartbeat"}
            continue
        if kind == "item":
            yield payload
        elif kind == "error":
            raise payload
        else:
            return


def _post_with_retry(payload: dict):
    """POST to OpenRouter, retrying transient failures (429 / 5xx / network errors)
    with exponential backoff. Non-transient errors (e.g. 400/401) raise immediately.
    Yields a {"type": "retry", ...} progress dict before each retry wait, then a
    final {"type": "response", "response": ...} once a request succeeds."""
    last_exc = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120,
            )
        except requests.exceptions.RequestException as exc:
            last_exc = exc
        else:
            if response.status_code == 429 or response.status_code >= 500:
                last_exc = requests.exceptions.HTTPError(
                    f"{response.status_code} {response.reason} da OpenRouter",
                    response=response,
                )
            else:
                response.raise_for_status()
                yield {"type": "response", "response": response}
                return

        if attempt == MAX_RETRIES:
            raise last_exc

        delay = _retry_delay(attempt, last_exc)
        logger.warning(
            "Chamada à OpenRouter falhou (tentativa %d/%d): %s. Tentando novamente em %.1fs.",
            attempt + 1,
            MAX_RETRIES + 1,
            last_exc,
            delay,
        )
        yield {
            "type": "retry",
            "attempt": attempt + 1,
            "max_attempts": MAX_RETRIES + 1,
            "delay": delay,
            "error": str(last_exc),
        }
        time.sleep(delay)


def _retry_delay(attempt: int, exc: Exception) -> float:
    response = getattr(exc, "response", None)
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

    return BACKOFF_BASE_SECONDS * (2**attempt) + random.uniform(0, 0.5)


def _split_csv_and_notes(content: str) -> tuple:
    lines = content.strip().splitlines()
    csv_lines = []
    notes = []
    in_notes = False

    for line in lines:
        if re.search(r"pontos? de atenç[aã]o", line, re.IGNORECASE):
            in_notes = True
            continue
        if in_notes:
            stripped = line.strip(" -*\t")
            if stripped:
                notes.append(stripped)
        elif line.strip():
            csv_lines.append(line)

    return "\n".join(csv_lines), notes
