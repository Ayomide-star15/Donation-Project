import re


PHONE_PATTERN = re.compile(r"(\+?234|0)[789][01]\d{8}")
EMAIL_PATTERN = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")
HANDLE_PATTERN = re.compile(r"@\w{3,}")
DIGIT_RUN = re.compile(r"\d{6,}")
NAME_PATTERN = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+",
    re.IGNORECASE,
)


def sanitize_note(note: str | None, max_length: int = 100) -> str | None:
    """Sanitize a requester's note before showing it to donors."""
    if not note:
        return None

    text = note.strip()
    text = PHONE_PATTERN.sub("", text)
    text = EMAIL_PATTERN.sub("", text)
    text = URL_PATTERN.sub("", text)
    text = HANDLE_PATTERN.sub("", text)
    text = DIGIT_RUN.sub("", text)
    text = NAME_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 5:
        return None
    if len(text) > max_length:
        text = text[:max_length].rstrip() + "…"
    return text