"""Armazenamento de usuários criados pela tela de registro.

Um SQLite local (`server/users.db`, gitignorado) com a senha guardada como hash scrypt.
O par `APP_USERNAME`/`APP_PASSWORD` do `.env` NÃO fica aqui — continua sendo a conta raiz,
verificada direto contra as variáveis de ambiente em `auth.check_credentials`.
"""

import base64
import hashlib
import hmac
import os
import re
import sqlite3
from datetime import datetime, timezone

import config

# Parâmetros do scrypt (RFC 7914). n=2**14 com r=8 usa ~16 MB por hash.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
DK_LEN = 32

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
MIN_PASSWORD_LENGTH = 8


class UserError(Exception):
    """Erro de validação/conflito com mensagem pronta para o usuário final."""


def _connect():
    conn = sqlite3.connect(config.USERS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def hash_password(password: str) -> str:
    salt = os.urandom(SALT_BYTES)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DK_LEN,
    )
    return "$".join(
        [
            "scrypt",
            str(SCRYPT_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(derived).decode("ascii"),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(hash_b64)),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, base64.b64decode(hash_b64))


def validate_new_user(username: str, password: str) -> None:
    """Levanta UserError com a mensagem em português se usuário/senha não servirem."""
    if not USERNAME_PATTERN.match(username or ""):
        raise UserError(
            "Usuário deve ter de 3 a 32 caracteres, usando apenas letras, números, ponto, "
            "hífen ou underscore."
        )
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise UserError(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if config.APP_USERNAME and username.lower() == config.APP_USERNAME.lower():
        raise UserError("Este nome de usuário já está em uso.")


def create_user(username: str, password: str) -> None:
    validate_new_user(username, password)
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, hash_password(password), created_at),
            )
    except sqlite3.IntegrityError:
        raise UserError("Este nome de usuário já está em uso.")


def authenticate(username: str, password: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        # Gasta o mesmo tempo de um hash real para não vazar quais usuários existem.
        hash_password(password)
        return False
    return verify_password(password, row["password_hash"])


def count_users() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
