import base64
import hashlib
import hmac
import json
import time
from functools import wraps

from flask import jsonify, request

import config
import users

SESSAO_INVALIDA = "Sessão expirada ou inválida. Faça login novamente."


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload_b64: str) -> str:
    digest = hmac.new(
        config.AUTH_SECRET.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64encode(digest)


def check_credentials(username: str, password: str) -> bool:
    """Aceita a conta raiz do .env ou qualquer usuário criado em /register."""
    usuario_ok = hmac.compare_digest(
        (username or "").encode("utf-8"), (config.APP_USERNAME or "").encode("utf-8")
    )
    senha_ok = hmac.compare_digest(
        (password or "").encode("utf-8"), (config.APP_PASSWORD or "").encode("utf-8")
    )
    if usuario_ok and senha_ok:
        return True
    return users.authenticate(username, password)


def check_registration_secret(secret: str) -> bool:
    """Confere o segredo digitado na tela de registro em tempo constante."""
    if not config.REGISTRATION_ENABLED:
        return False
    return hmac.compare_digest(
        (secret or "").encode("utf-8"), (config.REGISTRATION_SECRET or "").encode("utf-8")
    )


def create_token(username: str):
    """Devolve (token, expira_em_epoch). Token = base64(payload).base64(hmac)."""
    expires_at = int(time.time() + config.AUTH_TOKEN_TTL_HOURS * 3600)
    payload = json.dumps({"sub": username, "exp": expires_at}, separators=(",", ":"))
    payload_b64 = _b64encode(payload.encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64)}", expires_at


def verify_token(token: str):
    """Devolve o usuário do token se a assinatura confere e não expirou, senão None."""
    if not token or token.count(".") != 1:
        return None

    payload_b64, signature = token.split(".")
    if not hmac.compare_digest(signature, _sign(payload_b64)):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    if float(payload.get("exp", 0)) < time.time():
        return None

    return payload.get("sub")


def bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return value.strip()


def login_required(view):
    """Bloqueia a rota com 401 quando não há um Bearer token válido."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not verify_token(bearer_token()):
            # Mesmo formato dos eventos NDJSON, para o frontend conseguir exibir a mensagem
            # mesmo se ler a resposta como stream.
            return jsonify({"stage": "erro", "message": SESSAO_INVALIDA}), 401
        return view(*args, **kwargs)

    return wrapper
