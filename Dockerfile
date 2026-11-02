FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && python -m spacy download en_core_web_lg

COPY app ./app
COPY ui ./ui

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# The API key comes from the environment at run time: docker run --env-file .env ...
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
