"""Error classes. The client only ever sees a generic message; logs see the class."""

CLIENT_MESSAGE = "Could not read this document."


class PipelineError(Exception):
    """Raised with a short machine-readable class such as 'ocr_empty' or 'schema_invalid'.

    Never put OCR text, prompts, model output or field values in the message.
    """

    def __init__(self, error_class: str, request_id: str | None = None):
        super().__init__(error_class)
        self.error_class = error_class
        self.request_id = request_id
