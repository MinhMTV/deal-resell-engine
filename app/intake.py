import json
import re
from pathlib import Path
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from app.config import SOURCES, EXPIRED_MARKERS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "state" / "cursors.json"


def _extract_price(text: str):
    if not text:
        return None
    m = re.search(r"(\d+[\.,]?\d*)\s?€", text)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))


def is_expired_title(title: str):
    t = (title or "").lower()
    return any(marker in t for marker in EXPIRED_MARKERS)


def load_cursors():
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_cursors(cursors: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(cursors, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _parse_markdown_deals(markdown: str, source: str, stop_url: str | None = None):
    deals = []
    seen = set()
    for line in markdown.splitlines():
        if "/deals/" not in line:
            continue

        m_hot = re.search(r'\]\((https?://[^\s\)]+)\s+"([^"]+)"\)\s*$', line)
        if m_hot and "/deals/" in m_hot.group(1):
            url = m_hot.group(1).strip()
            title = m_hot.group(2).strip().replace("**", "")
        else:
            matches = list(re.finditer(r"(!?)\[([^\]]+)\]\((https?://[^\s\)]+)", line))
            if not matches:
                continue

            chosen = None
            for mm in matches:
                bang, t, u = mm.group(1), mm.group(2), mm.group(3)
                if bang != "!" and "/deals/" in u:
                    chosen = (t, u)
                    break
            if chosen is None:
                continue

            title, url = chosen[0].strip().replace("**", ""), chosen[1].strip()

        if stop_url and url == stop_url:
            break

        if url in seen or is_expired_title(title):
            continue
        seen.add(url)

        temp_match = re.search(r"(\d{1,5})°", line)
        temperature = int(temp_match.group(1)) if temp_match else None

        deals.append(
            {
                "source": source,
                "title": title,
                "url": url,
                "price": _extract_price(line) or _extract_price(title),
                "votes": temperature,
                "posted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return deals


def fetch_live_source(source: str, stop_url: str | None = None):
    url = SOURCES[source]

    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "xml")
            items = []
            for item in soup.find_all("item")[:100]:
                title = item.title.text.strip() if item.title else ""
                link = item.link.text.strip() if item.link else ""
                desc = item.description.text if item.description else ""
                if stop_url and link == stop_url:
                    break
                if is_expired_title(title):
                    continue
                items.append(
                    {
                        "source": source,
                        "title": title,
                        "url": link,
                        "price": _extract_price(title) or _extract_price(desc),
                        "votes": None,
                        "posted_at": item.pubDate.text if item.pubDate else datetime.now(timezone.utc).isoformat(),
                    }
                )
            if items:
                return items, None
    except Exception:
        pass

    try:
        base = "http://www.mydealz.de/deals" if source == "mydealz" else "http://www.preisjaeger.at/deals"
        mirror = f"https://r.jina.ai/{base}"
        r = requests.get(mirror, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            deals = _parse_markdown_deals(r.text, source, stop_url=stop_url)
            return deals, None
        return [], f"{source}: fallback mirror HTTP {r.status_code}"
    except Exception as e:
        return [], f"{source}: fallback error {e}"


def fetch_sample(path="samples/deals_sample.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))
