import json
import re
import time
import random
from pathlib import Path
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from app.config import SOURCES, EXPIRED_MARKERS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "state" / "cursors.json"

CONTRACT_KEYWORDS = [
    "monat", "/mo", "mtl", "vertrag", "tarif", "allnet", "flat",
    "zuzahlung", "magenta", "mobilfunk", "netz",
    "o2", "vodafone", "telekom", "otelo", "congstar", "1und1",
    "sim only", "5g", "gb", "mobil",
]
CONTRACT_MONTHS_DEFAULT = 24

BUNDLE_KEYWORDS = [
    "bundle", "im bundle", "eintausch", "tauschbonus", "trade-in",
    "gutschein", "speicher-upgrade", "zugabe", "dazu", "gratis",
    "cashback", "rabatt auf", "% auf",
]


def _parse_eur_amount(text: str) -> float | None:
    """Parse '9,99' or '199' or '9.99' from text."""
    m = re.search(r"(\d{1,5}[\.,]\d{1,2})\s*(?:€|EUR)", text)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d{1,5})\s*(?:€|EUR)", text)
    if m:
        return float(m.group(1))
    return None


def detect_contract_deal(deal: dict) -> dict:
    """
    Detect if a deal is a contract (Vertrag) deal and extract pricing.
    Returns enriched deal dict with contract fields added.
    """
    title = (deal.get("title") or "").lower()
    if not any(kw in title for kw in CONTRACT_KEYWORDS):
        deal["is_contract"] = False
        return deal

    # Extract monthly rate: '9,99€/Monat' or '39,95€/mo' or '9,99€ mtl'
    monthly = None
    m = re.search(r"(\d{1,3}[\.,]\d{1,2})\s*(?:€|EUR)\s*(?:/\s*(?:Monat|mo|mtl)|\s*(?:mtl|pro\s*Monat))", title)
    if m:
        monthly = float(m.group(1).replace(",", "."))

    # Extract upfront/Zuzahlung: '199€ Zuzahlung' or '559€ Zuzahlung'
    upfront = None
    m = re.search(r"(\d{1,4})\s*(?:€|EUR)\s*(?:Zuzahlung|Anzahlung|Vorauszahlung)", title, re.IGNORECASE)
    if m:
        upfront = float(m.group(1))

    # Contract duration: default 24 months, check title
    months = CONTRACT_MONTHS_DEFAULT
    m = re.search(r"(\d{1,2})\s*(?:Monate|Monaten|months|Mo\.|Laufzeit)", title)
    if m:
        months = int(m.group(1))

    # Calculate effective total
    total = None
    if upfront is not None and monthly is not None:
        total = round(upfront + (monthly * months), 2)
    elif monthly is not None:
        total = round(monthly * months, 2)
    elif upfront is not None:
        total = upfront

    deal["is_contract"] = True
    deal["contract_monthly"] = monthly
    deal["contract_months"] = months
    deal["contract_upfront"] = upfront
    deal["contract_total"] = total

    return deal


def detect_bundle_deal(deal: dict) -> dict:
    """Detect if a deal includes bundles, trade-in bonuses, or conditional pricing."""
    title = (deal.get("title") or "").lower()
    if any(kw in title for kw in BUNDLE_KEYWORDS):
        deal["is_bundle"] = True
        # Try to find the reason
        reasons = [kw for kw in BUNDLE_KEYWORDS if kw in title]
        deal["bundle_reason"] = ", ".join(reasons[:3])
    else:
        deal["is_bundle"] = False
        deal["bundle_reason"] = None
    return deal


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


def _is_probably_image_url(url: str) -> bool:
    u = (url or "").lower()
    return any(u.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"])


def _parse_markdown_deals(markdown: str, source: str, stop_url: str | None = None):
    deals = []
    seen = set()
    stop_hit = False
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
            stop_hit = True
            break

        if (
            url in seen
            or "/deals/" not in url
            or _is_probably_image_url(url)
            or title.lower().startswith("![image")
            or is_expired_title(title)
        ):
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
    return deals, stop_hit


def fetch_live_source(source: str, stop_url: str | None = None, max_pages: int = 1):
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
        all_deals = []
        seen_urls = set()

        for page in range(1, max(1, int(max_pages)) + 1):
            page_url = base if page == 1 else f"{base}?page={page}"
            mirror = f"https://r.jina.ai/{page_url}"

            # Throttle: respect rate limits with jittered delay between pages
            if page > 1:
                time.sleep(2.0 + random.uniform(0.5, 1.5))

            max_retries = 3
            backoff = 3.0
            r = None
            for attempt in range(max_retries):
                try:
                    r = requests.get(mirror, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
                    if r.status_code == 429:
                        wait = backoff + random.uniform(0.5, 1.5)
                        time.sleep(wait)
                        backoff *= 2
                        continue
                    break
                except Exception:
                    if attempt == max_retries - 1:
                        return all_deals, f"{source}: connection error on page {page}"
                    time.sleep(backoff + random.uniform(0.5, 1.5))
                    backoff *= 2

            if r is None or r.status_code != 200:
                status = r.status_code if r is not None else "no response"
                return all_deals, f"{source}: fallback mirror HTTP {status} on page {page}"

            page_deals, stop_hit = _parse_markdown_deals(r.text, source, stop_url=stop_url)
            for d in page_deals:
                if d["url"] in seen_urls:
                    continue
                seen_urls.add(d["url"])
                all_deals.append(d)

            if stop_hit:
                break

        return all_deals, None
    except Exception as e:
        return [], f"{source}: fallback error {e}"


def fetch_sample(path="samples/deals_sample.json"):
    return json.loads(Path(path).read_text(encoding="utf-8"))
