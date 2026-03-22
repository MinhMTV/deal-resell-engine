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
    # iPhones
    r"\biphone\s?(?:\d{1,2}|se)(?:\s?(?:pro\s?max|pro|max|plus))?\b",
    # Samsung Galaxy S/A/Z series
    r"\bgalaxy\s?(?:s|a|z)\d{1,2}(?:\s?(?:ultra|plus|fe))?\b",
    # Google Pixel
    r"\bpixel\s?\d{1,2}(?:\s?(?:pro|xl|a))?\b",
    # iPads (incl. generation numbers)
    r"\bipad\s?(?:air|mini|pro)?\s?\d{0,2}\b",
    # MacBooks (incl. M-chip gen + Neo)
    r"\bmacbook\s?(?:air|pro|neo)(?:\s?m\d)?\b",
    # Samsung Galaxy Tab
    r"\bgalaxy\s?tab\s?(?:s|a)\d{0,2}(?:\s?(?:ultra|plus|fe|lite))?\b",
    # OnePlus Pad
    r"\boneplus\s?pad\s?(?:go|pro)?\s?\d{0,2}\b",
    # Gaming consoles & handhelds
    r"\bplaystation\s?\d(?:\s?(?:slim|digital|pro))?\b",
    r"\bps\s?\d(?:\s?(?:slim|digital|pro))?\b",
    r"\bxbox\s?(?:series\s?[xs]|one)\b",
    r"\bswitch\s?(?:oled|lite)?\b",
    r"\bsteam\s?deck\b",
    r"\brog\s?(?:xbox\s?)?ally\b",
    r"\blegion\s?go\b",
    # Smartwatches
    r"\bapple\s?watch\s?(?:se|ultra)?\s?\d{0,2}\b",
    r"\bgalaxy\s?watch\s?\d{0,2}(?:\s?(?:classic|ultra|pro))?\b",
    r"\boneplus\s?watch\s?\d{0,2}\b",
    # Audio (earbuds/headphones)
    r"\bairpods?\s?(?:pro|max)?\s?\d{0,2}\b",
    # Apple accessories
    r"\bairtag\b",
    r"\bgalaxy\s?buds?\s?(?:pro|fe)?\s?\d{0,2}\b",
    # Laptops (ThinkPad, Surface, XPS)
    r"\bthinkpad\s?\w{1,5}\d{0,2}\b",
    r"\bsurface\s?(?:pro|laptop|go|studio)\s?\d{0,2}\b",
    r"\bxps\s?\d{1,2}\b",
    # E-readers
    r"\bkindle\s?(?:paperwhite|scribe|oasis)?\s?\d{0,2}\b",
    # Drones & action cams
    r"\bdji\s?(?:mini|air|mavic|avata|neo)\s?\d{0,2}\b",
    r"\bgopro\s?(?:hero|max)\s?\d{0,2}\b",
]


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def extract_storage_gb(title: str):
    t = (title or "").lower()
    matches = list(re.finditer(r"\b(\d{1,4})\s?(tb|gb)\b", t))
    if not matches:
        return None

    # Prefer capacities that look like real device storage over RAM mentions.
    storage_context = ("ssd", "hdd", "nvme", "storage", "speicher", "rom")
    ram_context = ("ram", "arbeitsspeicher")

    scored = []
    for m in matches:
        size = int(m.group(1))
        unit = m.group(2)
        size_gb = size * 1024 if unit == "tb" else size

        # Small context window around the match for lightweight heuristics.
        start = max(0, m.start() - 18)
        end = min(len(t), m.end() + 18)
        window = t[start:end]

        score = 0
        if any(k in window for k in storage_context):
            score += 3
        if any(k in window for k in ram_context):
            score -= 3

        # Real storage for resale is usually >= 64GB for phones/laptops.
        if size_gb >= 64:
            score += 1

        scored.append((score, size_gb))

    # Highest heuristic score wins; ties break towards larger capacity.
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][1]


def extract_brand(title: str):
    t = (title or "").lower()
    for b in KNOWN_BRANDS:
        if re.search(rf"\b{re.escape(b)}\b", t):
            return b
    return None


def extract_model(title: str):
    t = _normalize_space((title or "").lower())

    # MacBook enrichment: append chip generation when present (e.g. m4).
    m_mb = re.search(r"\bmacbook\s?(air|pro)\b", t)
    if m_mb:
        chip = re.search(r"\bm(\d)\b", t)
        base = f"macbook {m_mb.group(1)}"
        if chip:
            return f"{base} m{chip.group(1)}"
        return base

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
