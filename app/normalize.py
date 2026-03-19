import re


KNOWN_BRANDS = [
    "apple",
    "samsung",
    "google",
    "xiaomi",
    "sony",
    "nintendo",
    "microsoft",
    "lenovo",
    "hp",
    "dell",
    "asus",
    "acer",
]

COLOR_ALIASES = {
    "schwarz": "black",
    "black": "black",
    "weiß": "white",
    "weiss": "white",
    "white": "white",
    "silber": "silver",
    "silver": "silver",
    "grau": "gray",
    "gray": "gray",
    "gold": "gold",
    "blau": "blue",
    "blue": "blue",
    "rot": "red",
    "red": "red",
    "grün": "green",
    "gruen": "green",
    "green": "green",
    "violett": "purple",
    "purple": "purple",
    "pink": "pink",
}


MODEL_PATTERNS = [
    r"\biphone\s?(?:\d{1,2}|se)\b",
    r"\bgalaxy\s?(?:s|a|z)\d{1,2}\b",
    r"\bpixel\s?\d{1,2}(?:\s?(?:pro|xl|a))?\b",
    r"\bipad\s?(?:air|mini|pro)?\s?\d{0,2}\b",
    r"\bmacbook\s?(?:air|pro)?\b",
    r"\bplaystation\s?\d\b",
    r"\bps\d\b",
    r"\bxbox\s?(?:series\s?[xs]|one)\b",
    r"\bswitch\s?(?:oled|lite)?\b",
]


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def extract_storage_gb(title: str):
    t = (title or "").lower()
    m = re.search(r"\b(\d{1,4})\s?(tb|gb)\b", t)
    if not m:
        return None
    size = int(m.group(1))
    unit = m.group(2)
    if unit == "tb":
        size *= 1024
    return size


def extract_brand(title: str):
    t = (title or "").lower()
    for b in KNOWN_BRANDS:
        if re.search(rf"\b{re.escape(b)}\b", t):
            return b
    return None


def extract_model(title: str):
    t = _normalize_space((title or "").lower())
    for pattern in MODEL_PATTERNS:
        m = re.search(pattern, t)
        if m:
            return _normalize_space(m.group(0))
    return None


def extract_color(title: str):
    t = (title or "").lower()
    for raw, normalized in COLOR_ALIASES.items():
        if re.search(rf"\b{re.escape(raw)}\b", t):
            return normalized
    return None


def normalize_product(title: str) -> dict:
    return {
        "normalized_brand": extract_brand(title),
        "normalized_model": extract_model(title),
        "normalized_storage_gb": extract_storage_gb(title),
        "normalized_color": extract_color(title),
    }
