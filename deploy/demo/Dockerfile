# The fellowship live demo: API and Streamlit page behind one port, with no database or queue.
# Build from the repo root: docker build -f deploy/demo/Dockerfile -t meridian-demo .
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils caddy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -m spacy download en_core_web_lg

COPY app ./app
COPY ui ./ui
COPY deploy/demo/Caddyfile deploy/demo/start.sh ./deploy/

# Run as a normal user. Uid 1000 is also what Hugging Face Spaces expects.
RUN useradd -u 1000 -m demo && mkdir -p /app/.uploads /app/logs && chown -R demo /app && chmod +x /app/deploy/start.sh
USER demo

ENV PYTHONUNBUFFERED=1 OTEL_CONSOLE_EXPORT=0 PORT=7860 XDG_DATA_HOME=/tmp XDG_CONFIG_HOME=/tmp
EXPOSE 7860
CMD ["/app/deploy/start.sh"]
