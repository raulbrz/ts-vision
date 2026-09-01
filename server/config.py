import os
import secrets

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

# Opções do seletor de modelo na tela (todos multimodais/com suporte a imagem). A UI só deixa
# escolher um destes; a API (/api/settings/model) aceita qualquer string no formato
# "provedor/modelo" — não é uma allowlist, só a lista do <select>.
OPENROUTER_MODEL_OPTIONS = list(
    dict.fromkeys(
        [
            OPENROUTER_MODEL,
            "inclusionai/ling-3.0-flash:free",
            "deepseek/deepseek-v4-flash-0731",
            "qwen/qwen3.7-flash",
            "google/gemma-4-26b-a4b-it:free",
            "google/gemma-4-26b-a4b-it",
            "google/gemini-2.5-flash-lite",
            "xiaomi/mimo-v2.5"
            "deepseek/deepseek-v4-flash-vision-exp",
        ]
    )
)

APP_USERNAME = os.environ.get("APP_USERNAME")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

# Sem AUTH_SECRET no .env o servidor gera um segredo por processo: funciona, mas invalida
# todas as sessões a cada restart (inclusive o reload do debug=True).
AUTH_SECRET = os.environ.get("AUTH_SECRET") or secrets.token_hex(32)
AUTH_SECRET_IS_EPHEMERAL = not os.environ.get("AUTH_SECRET")

try:
    AUTH_TOKEN_TTL_HOURS = float(os.environ.get("AUTH_TOKEN_TTL_HOURS", "12"))
except ValueError:
    AUTH_TOKEN_TTL_HOURS = 12.0

# Segredo que autoriza a criação de conta em /register. Sem valor próprio, é o AUTH_SECRET
# — o que só funciona se ele estiver fixado no .env (senão é aleatório a cada start).
REGISTRATION_SECRET = os.environ.get("REGISTRATION_SECRET") or AUTH_SECRET
REGISTRATION_ENABLED = bool(os.environ.get("REGISTRATION_SECRET")) or not AUTH_SECRET_IS_EPHEMERAL

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DB_PATH = os.environ.get("USERS_DB_PATH") or os.path.join(BASE_DIR, "users.db")


def _env_number(name, default, cast=float):
    try:
        return cast(os.environ.get(name, default))
    except (TypeError, ValueError):
        return cast(default)


# Freio de força bruta em /api/login e /api/register (ver ratelimit.py).
# Até AUTH_MAX_ATTEMPTS falhas por IP dentro da janela só custam o atraso; a partir daí o
# IP é bloqueado por AUTH_BLOCK_SECONDS, dobrando a cada falha até AUTH_MAX_BLOCK_SECONDS.
AUTH_FAILURE_DELAY_SECONDS = _env_number("AUTH_FAILURE_DELAY_SECONDS", "1")
AUTH_MAX_ATTEMPTS = _env_number("AUTH_MAX_ATTEMPTS", "5", int)
AUTH_BLOCK_SECONDS = _env_number("AUTH_BLOCK_SECONDS", "30", int)
AUTH_MAX_BLOCK_SECONDS = _env_number("AUTH_MAX_BLOCK_SECONDS", "900", int)
AUTH_ATTEMPT_WINDOW_SECONDS = _env_number("AUTH_ATTEMPT_WINDOW_SECONDS", "900", int)


def validate() -> None:
    missing = []
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if not APP_USERNAME:
        missing.append("APP_USERNAME")
    if not APP_PASSWORD:
        missing.append("APP_PASSWORD")
    if missing:
        raise RuntimeError(
            "Variáveis de ambiente obrigatórias ausentes: "
            + ", ".join(missing)
            + ". Veja server/.env.example."
        )
