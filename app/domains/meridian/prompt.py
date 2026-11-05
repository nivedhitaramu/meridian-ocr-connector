"""The Meridian extraction prompt, from its configuration. Masked OCR text goes under these instructions."""
from .schemas import workflow

PROMPT_VERSION = workflow.config.prompt_version
SYSTEM_PROMPT = workflow.config.system_prompt
