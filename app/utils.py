import re


def sanitize(string: str) -> str:
    return re.sub(r"[\n\r\s]+", " ", string.strip())


def slugify(string: str) -> str:
    slug = re.sub(r"[^\w\d\s]", "", string.strip().lower())
    return re.sub(r"\s+", "-", slug)
