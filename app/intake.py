import json
import re
from pathlib import Path
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from app.config import SOURCES


def _extract_price(text: str):
    if not text:
        return None
    m = re.search(r"(\d+[\.,]?\d*)\s?€", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def fetch_live_source(source: str):
    url = SOURCES[source]
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return [], f"{source}: HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "xml")
        items = []
        for item in soup.find_all("item")[:100]:
            title = item.title.text.strip() if item.title else ""
            link = item.link.text.strip() if item.link else ""
            desc = item.description.text if item.description else ""
            items.append({
                "source": source,
                "title": title,
                "url": link,
                "price": _extract_price(title) or _extract_price(desc),
                "votes": None,
                "posted_at": item.pubDate.text if item.pubDate else datetime.utcnow().isoformat(),
            })
        return items, None
    except Exception as e:
        return [], f"{source}: {e}"


def fetch_sample(path="samples/deals_sample.json"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data
