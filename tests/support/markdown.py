import re


def sections(text: str) -> dict[str, str]:
    """Markdown heading -> the text up to the next heading."""
    parts = re.split(r"^#+ (.+)$", text, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))
