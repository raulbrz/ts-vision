"""Configurações alteráveis em tempo de execução (sem editar .env/redeploy) — hoje,
apenas qual modelo da OpenRouter processa o OCR. Persistidas no mesmo SQLite de
users.db (server/users.db), então sobrevivem a restarts, inclusive o volume Docker
usado em produção.
"""

import re
import sqlite3

import config

MODEL_KEY = "openrouter_model"

# Aceita slugs no formato "provedor/modelo" usado pela OpenRouter (letras, números,
# ponto, hífen, underscore, dois-pontos e barra), com um teto de tamanho generoso.
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+/[A-Za-z0-9._:-]+$")


class SettingsError(Exception):
    """Erro de validação com mensagem pronta para o usuário final."""


def _connect():
    conn = sqlite3.connect(config.USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def get_active_model() -> str:
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (MODEL_KEY,)
        ).fetchone()
    if row and row["value"]:
        return row["value"]
    return config.OPENROUTER_MODEL


def set_active_model(model: str) -> str:
    model = (model or "").strip()
    if len(model) > 200 or not MODEL_PATTERN.match(model):
        raise SettingsError(
            "Modelo inválido. Use o formato \"provedor/modelo\" da OpenRouter, "
            "ex.: google/gemini-2.5-flash-lite."
        )
    with _connect() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (MODEL_KEY, model),
        )
    return model
