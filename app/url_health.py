"""Deal URL Health Checker — verify if deal URLs are still accessible.

Checks deal URLs via HEAD requests and reports:
- Live deals (200 OK)
- Expired deals (404, 5xx, timeout)
- Redirects (deal might have moved)

Updates deal_pipeline stage to 'archived' for expired deals.
"""

import json
import sys
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

from app.deal_tracker import connect_tracker, list_deals, update_stage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEALTH_CACHE_PATH = PROJECT_ROOT / "state" / "url_health.json"


def _load_health_cache() -> dict:
    if not HEALTH_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(HEALTH_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_health_cache(data: dict):
    HEALTH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_url(url: str, timeout: int = 10) -> dict:
    """Check a single URL health.

    Returns:
        {
            "url": str,
            "status": "live" | "expired" | "redirect" | "error",
            "http_code": int | None,
            "final_url": str,
            "response_time_ms": int,
            "checked_at": str,
        }
    """
    if requests is None:
        return {
            "url": url,
            "status": "error",
            "http_code": None,
            "final_url": url,
            "response_time_ms": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": "requests not installed",
        }

    try:
        start = time.monotonic()
        resp = requests.head(url, timeout=timeout, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (DealEngine HealthCheck)"
        })
        elapsed_ms = int((time.monotonic() - start) * 1000)

        status = "live"
        if resp.status_code == 404:
            status = "expired"
        elif resp.status_code >= 500:
            status = "expired"
        elif resp.url != url and resp.status_code in (301, 302, 303, 307, 308):
            # Check if redirect target is also 200
            if resp.status_code == 200:
                status = "redirect"
            else:
                status = "expired"
        elif resp.status_code == 200:
            status = "live"

        return {
            "url": url,
            "status": status,
            "http_code": resp.status_code,
            "final_url": resp.url,
            "response_time_ms": elapsed_ms,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except requests.Timeout:
        return {
            "url": url,
            "status": "error",
            "http_code": None,
            "final_url": url,
            "response_time_ms": timeout * 1000,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": "timeout",
        }
    except Exception as e:
        return {
            "url": url,
            "status": "error",
            "http_code": None,
            "final_url": url,
            "response_time_ms": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": str(e)[:200],
        }


def check_pipeline_urls(
    stage: str | None = None,
    days: int = 30,
    max_urls: int = 20,
    timeout: int = 10,
    auto_archive: bool = False,
) -> dict:
    """Check health of all deal URLs in pipeline.

    Returns summary with live/expired/error counts and details.
    """
    conn = connect_tracker()
    deals = list_deals(conn, stage=stage, days=days, limit=max_urls)

    if not deals:
        return {"total": 0, "live": 0, "expired": 0, "error": 0, "details": []}

    cache = _load_health_cache()
    results = []
    live_count = 0
    expired_count = 0
    error_count = 0

    # Use thread pool for parallel checks
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for deal in deals:
            url = deal.get("deal_url", "")
            if not url:
                continue

            # Use cache if checked within last hour
            cached = cache.get(url)
            if cached and cached.get("checked_at", "") > (
                datetime.now(timezone.utc).isoformat()[:13]  # same hour
            ):
                result = cached
            else:
                future = executor.submit(check_url, url, timeout)
                futures[future] = deal

        # Collect results
        for deal in deals:
            url = deal.get("deal_url", "")
            if not url:
                continue

            cached = cache.get(url)
            if cached and cached.get("checked_at", "") > datetime.now(timezone.utc).isoformat()[:13]:
                result = cached
            else:
                # Find the future for this URL
                result = None
                for future, d in futures.items():
                    if d.get("deal_url") == url:
                        result = future.result()
                        cache[url] = result
                        break

            if result is None:
                result = check_url(url, timeout)
                cache[url] = result

            result["alert_key"] = deal.get("alert_key", "")
            result["model"] = deal.get("normalized_model", "")
            result["pipeline_stage"] = deal.get("stage", "")
            results.append(result)

            if result["status"] == "live":
                live_count += 1
            elif result["status"] == "expired":
                expired_count += 1
                # Auto-archive expired deals
                if auto_archive and deal.get("alert_key"):
                    update_stage(conn, deal["alert_key"], "archived", notes="Auto-archived: URL expired")
            else:
                error_count += 1

    _save_health_cache(cache)
    conn.close()

    return {
        "total": len(results),
        "live": live_count,
        "expired": expired_count,
        "error": error_count,
        "details": results,
    }


def format_health_report(health: dict) -> str:
    """Format health check as human-readable report."""
    lines = []
    total = health["total"]
    lines.append(f"🩺 **Deal-URL Health Check** ({total} URLs geprüft)\n")

    if total == 0:
        lines.append("Keine Deals zum Prüfen.")
        return "\n".join(lines)

    lines.append(f"✅ Live: {health['live']}")
    lines.append(f"❌ Expired: {health['expired']}")
    lines.append(f"⚠️ Error: {health['error']}")
    lines.append("")

    expired = [d for d in health["details"] if d["status"] == "expired"]
    errors = [d for d in health["details"] if d["status"] == "error"]

    if expired:
        lines.append("**❌ Abgelaufene Deals:**")
        for d in expired[:10]:
            model = (d.get("model") or "?").title()
            code = d.get("http_code", "?")
            lines.append(f"  • {model}: HTTP {code} — {d['url'][:80]}")
        lines.append("")

    if errors:
        lines.append("**⚠️ Fehler (Timeout/Netzwerk):**")
        for d in errors[:5]:
            model = (d.get("model") or "?").title()
            err = d.get("error", "unknown")
            lines.append(f"  • {model}: {err}")
        lines.append("")

    return "\n".join(lines)
