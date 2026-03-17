import json
import re
from pathlib import Path
from datetime import datetime, timezone
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


def _parse_markdown_deals(markdown: str, source: str):
    deals = []
    seen = set()
    # capture lines that include a deal URL; works for both normal and hot-list blocks
    for line in markdown.splitlines():
        if "/deals/" not in line:
            continue

        # Pattern A: hot list lines with image+text then final linked deal URL with quoted title
        m_hot = re.search(r'\]\((https?://[^\s\)]+)\s+"([^"]+)"\)\s*$', line)
        if m_hot and "/deals/" in m_hot.group(1):
            url = m_hot.group(1).strip()
            title = m_hot.group(2).strip().replace("**", "")
        else:
            # Pattern B: standard markdown links; prefer non-image links
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
        if url in seen:
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


def fetch_live_source(source: str):
    url = SOURCES[source]

    # 1) direct RSS/XML attempt
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "xml")
            items = []
            for item in soup.find_all("item")[:100]:
                title = item.title.text.strip() if item.title else ""
                link = item.link.text.strip() if item.link else ""
                desc = item.description.text if item.description else ""
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

    # 2) robust fallback via jina mirror (markdown extraction)
    try:
        base = "http://www.mydealz.de/deals" if source == "mydealz" else "http://www.preisjaeger.at/deals"
        mirror = f"https://r.jina.ai/{base}"
        r = requests.get(mirror, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            deals = _parse_markdown_deals(r.text, source)
            if deals:
                return deals, None
        return [], f"{source}: fallback mirror HTTP {r.status_code}"
    except Exception as e:
        return [], f"{source}: fallback error {e}"


def fetch_sample(path="samples/deals_sample.json"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data
