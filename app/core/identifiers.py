import secrets


def generate_reference_code(prefix: str) -> str:
    """Return a readable, non-sequential identifier suitable for support and URLs."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{prefix}-{suffix}"
