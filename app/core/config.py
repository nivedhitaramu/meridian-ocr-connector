"""Settings read from the environment. Never hard-code keys here."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is in requirements; tolerate its absence
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


# Which document workflow runs. See app/domains/registry.py.
DOMAIN = os.getenv("DOMAIN", "meridian")

# --- LLM -------------------------------------------------------------------
# "openai_compatible" works with Gemini, Groq, OpenRouter, Together, Ollama, LM Studio...
# "mock" is a regex extractor for offline development and CI. Never demo with it.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.1-flash-lite")
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 60)

# Vision fallback. Leave VISION_MODEL empty to return a manual-review error instead.
VISION_BASE_URL = os.getenv("VISION_BASE_URL", LLM_BASE_URL).rstrip("/")
VISION_API_KEY = os.getenv("VISION_API_KEY", LLM_API_KEY)
VISION_MODEL = os.getenv("VISION_MODEL", "")

# --- OCR -------------------------------------------------------------------
OCR_DPI = _int("OCR_DPI", 300)
MAX_PAGE_PIXELS = _int("MAX_PAGE_PIXELS", 25_000_000)  # A3 at 300 DPI is about 17 million
OCR_TIMEOUT_S = _int("OCR_TIMEOUT_S", 60)              # per step, so a hostile file can't hold a worker
OCR_MIN_ALNUM = _int("OCR_MIN_ALNUM", 40)      # fewer letters/digits -> fallback
OCR_MIN_CONFIDENCE = _int("OCR_MIN_CONFIDENCE", 60)
OCR_LANG = os.getenv("OCR_LANG", "eng")
# psm 4 = single column of variable-size text. psm 6 drops large title lines (lost "PACKING LIST").
OCR_PSM = _int("OCR_PSM", 4)

# --- PII -------------------------------------------------------------------
SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_lg")
PII_SCORE_THRESHOLD = float(os.getenv("PII_SCORE_THRESHOLD", "0.35"))

# --- Upload ----------------------------------------------------------------
MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_MB", 10) * 1024 * 1024
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./.uploads")).resolve()
MAX_EML_ATTACHMENTS = _int("MAX_EML_ATTACHMENTS", 10)
MAX_PDF_PAGES = _int("MAX_PDF_PAGES", 5)        # longer PDFs are refused, never silently cut short
VISION_MAX_PAGES = _int("VISION_MAX_PAGES", 3)  # longer fallback documents go to manual review

# Files waiting on background jobs: "local" for one machine, "s3" when the API and workers run apart.
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./.job-uploads")).resolve()
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "")
STORAGE_MAX_AGE_SECONDS = _int("STORAGE_MAX_AGE_SECONDS", 3600)  # older files were left behind by a crash

# --- Background jobs -------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# After a worker dies, Redis redelivers its job once this has passed. Keep it longer than the slowest job.
QUEUE_VISIBILITY_SECONDS = _int("QUEUE_VISIBILITY_SECONDS", 900)
JOB_MAX_ATTEMPTS = _int("JOB_MAX_ATTEMPTS", 3)

# --- Web -------------------------------------------------------------------
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",") if o.strip()]
RATE_LIMIT_PER_MINUTE = _int("RATE_LIMIT_PER_MINUTE", 30)  # per client, on the extract endpoints. 0 turns it off.
# Across all clients, per running copy. A public demo on a paid key needs this: each request costs money. 0 turns it off.
DAILY_EXTRACT_LIMIT = _int("DAILY_EXTRACT_LIMIT", 200)
API_KEY_RATE_LIMIT_PER_MINUTE = _int("API_KEY_RATE_LIMIT_PER_MINUTE", 120)  # per customer API key. 0 turns it off.
WEBHOOK_MAX_ATTEMPTS = _int("WEBHOOK_MAX_ATTEMPTS", 5)
WEBHOOK_ALLOW_PRIVATE = os.getenv("WEBHOOK_ALLOW_PRIVATE", "0") == "1"  # local development only
# When set, /v1/trace/last and /v1/metrics need this value in the X-Internal-Token header. Set it when deployed.
INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

# --- Database --------------------------------------------------------------
# Empty is fine for the stateless API, which doesn't use the database yet.
DATABASE_URL = os.getenv("DATABASE_URL", "")

# --- Sign-in ---------------------------------------------------------------
# Your Clerk Frontend API URL, for example https://your-app.clerk.accounts.dev. Empty refuses every token.
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "").rstrip("/")
CLERK_AUTHORIZED_PARTIES = [o.strip() for o in os.getenv("CLERK_AUTHORIZED_PARTIES", "http://localhost:3000").split(",") if o.strip()]

# --- Telemetry -------------------------------------------------------------
TELEMETRY_LOG = Path(os.getenv("TELEMETRY_LOG", "./logs/telemetry.jsonl")).resolve()
OTEL_CONSOLE_EXPORT = os.getenv("OTEL_CONSOLE_EXPORT", "1") == "1"
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
