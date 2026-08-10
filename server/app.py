import json
import logging
import os
import time

from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS

import auth
import config
import llm
import ocr
import ratelimit
import users

config.validate()
users.init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, "..", "prompt-to-OCR")

with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    PROMPT_TEMPLATE = f.read()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if config.AUTH_SECRET_IS_EPHEMERAL:
    logger.warning(
        "AUTH_SECRET não definido no .env — usando um segredo temporário; "
        "as sessões serão invalidadas a cada reinício do servidor."
    )


limiter = ratelimit.AttemptLimiter(
    max_attempts=config.AUTH_MAX_ATTEMPTS,
    base_block_seconds=config.AUTH_BLOCK_SECONDS,
    max_block_seconds=config.AUTH_MAX_BLOCK_SECONDS,
    window_seconds=config.AUTH_ATTEMPT_WINDOW_SECONDS,
)


def _event(stage, message, **extra):
    payload = {"stage": stage, "message": message, **extra}
    return json.dumps(payload) + "\n"


def _rate_key(scope):
    # Sem proxy reverso na frente, remote_addr é o IP real; atrás de um, isso vira o IP do
    # proxy e o freio passa a ser global — aí é preciso tratar X-Forwarded-For.
    return f"{scope}:{request.remote_addr or 'desconhecido'}"


def _too_many_attempts(retry_after):
    response = jsonify(
        {
            "message": "Muitas tentativas. Tente novamente em "
            f"{retry_after} segundo(s)."
        }
    )
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


def _penalize(key):
    """Aplica o atraso da tentativa falha e devolve o bloqueio resultante, se houver."""
    block = limiter.register_failure(key)
    if config.AUTH_FAILURE_DELAY_SECONDS > 0:
        time.sleep(config.AUTH_FAILURE_DELAY_SECONDS)
    return block


@app.route("/api/login", methods=["POST"])
def login_endpoint():
    data = request.get_json(silent=True) or {}
    username = (data.get("usuario") or "").strip()
    password = data.get("senha") or ""

    key = _rate_key("login")
    retry_after = limiter.retry_after(key)
    if retry_after:
        return _too_many_attempts(retry_after)

    if not username or not password:
        return jsonify({"message": "Informe usuário e senha."}), 400

    if not auth.check_credentials(username, password):
        block = _penalize(key)
        logger.warning("Login inválido para %r vindo de %s", username, request.remote_addr)
        if block:
            return _too_many_attempts(block)
        return jsonify({"message": "Usuário ou senha inválidos."}), 401

    limiter.reset(key)
    token, expires_at = auth.create_token(username)
    return jsonify({"token": token, "usuario": username, "expira_em": expires_at})


@app.route("/api/register", methods=["POST"])
def register_endpoint():
    data = request.get_json(silent=True) or {}
    username = (data.get("usuario") or "").strip()
    password = data.get("senha") or ""
    secret = data.get("segredo") or ""

    if not config.REGISTRATION_ENABLED:
        return (
            jsonify(
                {
                    "message": "Registro indisponível: defina AUTH_SECRET (ou "
                    "REGISTRATION_SECRET) no server/.env."
                }
            ),
            503,
        )

    key = _rate_key("register")
    retry_after = limiter.retry_after(key)
    if retry_after:
        return _too_many_attempts(retry_after)

    if not username or not password or not secret:
        return jsonify({"message": "Informe usuário, senha e o segredo de registro."}), 400

    if not auth.check_registration_secret(secret):
        block = _penalize(key)
        logger.warning(
            "Tentativa de registro com segredo inválido para o usuário %r vindo de %s",
            username,
            request.remote_addr,
        )
        if block:
            return _too_many_attempts(block)
        return jsonify({"message": "Segredo de registro inválido."}), 403

    limiter.reset(key)

    try:
        users.create_user(username, password)
    except users.UserError as exc:
        # Conflito de nome vira 409; regras de formato/tamanho viram 400.
        status = 409 if "já está em uso" in str(exc) else 400
        return jsonify({"message": str(exc)}), status

    logger.info("Usuário %r criado via /api/register", username)
    token, expires_at = auth.create_token(username)
    return jsonify({"token": token, "usuario": username, "expira_em": expires_at}), 201


@app.route("/api/session", methods=["GET"])
def session_endpoint():
    username = auth.verify_token(auth.bearer_token())
    if not username:
        return jsonify({"message": auth.SESSAO_INVALIDA}), 401
    return jsonify({"usuario": username})


@app.route("/api/ocr", methods=["POST"])
@auth.login_required
def ocr_endpoint():
    files = request.files.getlist("files")
    date_start = request.form.get("data_inicial", "").strip()
    date_end = request.form.get("data_final", "").strip()

    if not files:
        return Response(_event("erro", "Nenhum arquivo enviado."), mimetype="application/x-ndjson")
    if not date_start or not date_end:
        return Response(
            _event("erro", "Informe data inicial e data final."), mimetype="application/x-ndjson"
        )

    file_records = [(fs.filename, fs.read()) for fs in files]

    def generate():
        yield _event("recebido", "Arquivos recebidos, iniciando OCR...")

        ocr_texts = {}
        notes = []

        for filename, file_bytes in file_records:
            yield _event("ocr_lendo", f"Lendo {filename} com OCR...", arquivo=filename)
            try:
                ocr_texts[filename] = ocr.extract_text(file_bytes, filename)
                yield _event(
                    "ocr_concluido", f"OCR de {filename} concluído.", arquivo=filename
                )
            except Exception as exc:
                logger.exception("Falha no OCR de %s", filename)
                notes.append(f"{filename}: falha no OCR ({exc})")
                yield _event("ocr_falhou", f"Falha no OCR de {filename}.", arquivo=filename)

        if not ocr_texts:
            yield _event("erro", "Nenhum arquivo pôde ser processado pelo OCR.")
            return

        yield _event("llm_processando", "Ajustando texto extraído com IA...")

        try:
            csv_text, llm_notes = llm.structure(ocr_texts, date_start, date_end, PROMPT_TEMPLATE)
        except Exception as exc:
            logger.exception("Falha ao chamar o LLM")
            yield _event("erro", f"Falha ao processar com o LLM: {exc}")
            return

        yield _event(
            "concluido", "Concluído.", csv=csv_text, notes=notes + llm_notes
        )

    return Response(stream_with_context(generate()), mimetype="application/x-ndjson")


if __name__ == "__main__":
    app.run(port=5000, debug=True)
