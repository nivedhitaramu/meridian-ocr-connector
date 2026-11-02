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


# --- LLM -------------------------------------------------------------------
# "openai_compatible" works with Groq, OpenRouter, Together, Ollama, LM Studio...
# "mock" is a regex extractor for offline development and CI. Never demo with it.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 60)
PROMPT_VERSION = "meridian-v1"

# Vision fallback. Leave VISION_MODEL empty to return a manual-review error instead.
VISION_BASE_URL = os.getenv("VISION_BASE_URL", LLM_BASE_URL).rstrip("/")
VISION_API_KEY = os.getenv("VISION_API_KEY", LLM_API_KEY)
VISION_MODEL = os.getenv("VISION_MODEL", "")

# --- OCR -------------------------------------------------------------------
OCR_DPI = _int("OCR_DPI", 300)
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

# --- Web -------------------------------------------------------------------
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",") if o.strip()]
RATE_LIMIT_PER_MINUTE = _int("RATE_LIMIT_PER_MINUTE", 30)  # per client, on the extract endpoints. 0 turns it off.
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
