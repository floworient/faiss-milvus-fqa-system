from uuid import uuid4


def new_id(prefix: str) -> str:
    """Return an opaque identifier with a readable resource prefix."""

    normalized = prefix.strip().rstrip("_")
    if not normalized:
        raise ValueError("prefix must not be empty")
    return f"{normalized}_{uuid4().hex}"

