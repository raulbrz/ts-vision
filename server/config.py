import os
import secrets

from dotenv import load_dotenv

load_dotenv()

GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

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


def validate() -> None:
    missing = []
    if not GOOGLE_APPLICATION_CREDENTIALS:
        missing.append("GOOGLE_APPLICATION_CREDENTIALS")
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
