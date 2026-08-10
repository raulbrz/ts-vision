FROM python:3.11-slim

WORKDIR /app/server

COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY server/ .
COPY prompt-to-OCR /app/prompt-to-OCR

EXPOSE 5000

# workers=1: config.py generates a random AUTH_SECRET per process when none is set in
# .env, so multiple worker processes would sign tokens with different secrets and fail
# to verify each other's. Threads give request concurrency without that split-brain.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "1", "--threads", "8", "--timeout", "600", "app:app"]
