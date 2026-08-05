import logging
import random
import re
import time

import requests

import config

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1

logger = logging.getLogger(__name__)


def structure(
    ocr_texts: dict, date_start: str, date_end: str, prompt_template: str
) -> tuple:
    prompt = prompt_template.replace("[DATA_INICIAL]", date_start).replace(
        "[DATA_FINAL]", date_end
    )

    sources = "\n\n".join(
        f"--- Texto extraído de {filename} ---\n{text}"
        for filename, text in ocr_texts.items()
    )

    user_message = f"{prompt}\n\nTEXTOS EXTRAÍDOS POR OCR:\n\n{sources}"

    response = _post_with_retry(
        {
            "model": config.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": user_message}],
        }
    )
    content = response.json()["choices"][0]["message"]["content"]

    return _split_csv_and_notes(content)


def _post_with_retry(payload: dict):
    """POST to OpenRouter, retrying transient failures (429 / 5xx / network errors)
    with exponential backoff. Non-transient errors (e.g. 400/401) raise immediately."""
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
                return response

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
