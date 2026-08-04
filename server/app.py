import logging
import os

from flask import Flask, jsonify, request
from flask_cors import CORS

import config
import llm
import ocr

config.validate()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPT_PATH = os.path.join(BASE_DIR, "..", "prompt-to-OCR")

with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    PROMPT_TEMPLATE = f.read()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route("/api/ocr", methods=["POST"])
def ocr_endpoint():
    files = request.files.getlist("files")
    date_start = request.form.get("data_inicial", "").strip()
    date_end = request.form.get("data_final", "").strip()

    if not files:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400
    if not date_start or not date_end:
        return jsonify({"error": "Informe data inicial e data final."}), 400

    ocr_texts = {}
    notes = []

    for file_storage in files:
        filename = file_storage.filename
        file_bytes = file_storage.read()
        try:
            ocr_texts[filename] = ocr.extract_text(file_bytes, filename)
        except Exception as exc:
            logger.exception("Falha no OCR de %s", filename)
            notes.append(f"{filename}: falha no OCR ({exc})")

    if not ocr_texts:
        return jsonify({"error": "Nenhum arquivo pôde ser processado pelo OCR."}), 502

    try:
        csv_text, llm_notes = llm.structure(ocr_texts, date_start, date_end, PROMPT_TEMPLATE)
    except Exception as exc:
        logger.exception("Falha ao chamar o LLM")
        return jsonify({"error": f"Falha ao processar com o LLM: {exc}"}), 502

    return jsonify({"csv": csv_text, "notes": notes + llm_notes})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
