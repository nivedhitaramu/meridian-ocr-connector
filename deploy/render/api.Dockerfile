# The product API for a free 512 MB host, such as Render's free instance, for a prototype link.
# Runs scripts/run_local.py: SQLite inside the container and background work in threads, so there's no database
# or queue to pay for. Data is lost whenever the host restarts the container. Not for real use.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -m spacy download en_core_web_sm

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY scripts/run_local.py ./scripts/run_local.py

RUN useradd -u 1000 -m api && chown -R api /app
USER api

ENV PYTHONUNBUFFERED=1 OTEL_CONSOLE_EXPORT=0 HOST=0.0.0.0 PORT=8000 SPACY_MODEL=en_core_web_sm \
    DAILY_EXTRACT_LIMIT=50 MAX_EML_ATTACHMENTS=4 LLM_PROVIDER=openai_compatible
EXPOSE 8000
CMD ["python", "scripts/run_local.py"]
