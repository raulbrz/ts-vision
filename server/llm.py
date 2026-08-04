import re

import requests

import config

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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

    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": user_message}],
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    return _split_csv_and_notes(content)


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
