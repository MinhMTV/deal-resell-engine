"""Deal urgency detection from deal text.

Detects urgency signals in German deal posts:
- Stock urgency: "nur noch X verfügbar", "nur noch X Stück"
- Time urgency: "endet heute", "nur heute", "bis XX.XX", "limitiert"
- Flash deals: "Kurzzeitig", "flash sale", "Blitzangebot"
- Low stock indicators: "wenige Stücke", "nur X übrig"

Returns an urgency dict with level, signals, and details.
"""

import re
from typing import Optional


# Urgency patterns (compiled for performance)
_PATTERNS = {
    "stock_low": [
        re.compile(r"nur\s+noch\s+(\d+)\s*(Stück|verfügbar|übrig|Stk)", re.I),
        re.compile(r"nur\s+noch\s+(\d+)\s+(?:exemplar|item)", re.I),
        re.compile(r"nur\s+(\d+)\s+(?:Stück|Stk)\s+verfügbar", re.I),
        re.compile(r"only\s+(\d+)\s+left", re.I),
        re.compile(r"bestand:\s*(\d+)", re.I),
    ],
    "stock_phrase": [
        re.compile(r"nur\s+noch\s+wenige", re.I),
        re.compile(r"nur\s+noch\s+einen?\s+Augenblick", re.I),
        re.compile(r"begrenzte?\s+(Menge|Anzahl|Stückzahl)", re.I),
        re.compile(r"wenige\s+(?:Stücke?|Exemplare)\s+(?:vorhanden|verfügbar|übrig)", re.I),
        re.compile(r"ausverkauf\s+näher", re.I),
    ],
    "time_limited": [
        re.compile(r"(endet|läuft ab|verfällt)\s+(heute|bald|gleich)", re.I),
        re.compile(r"nur\s+heute", re.I),
        re.compile(r"nur\s+(?:für\s+)?(?:kurze\s+Zeit|heute)", re.I),
        re.compile(r"bis\s+\d{1,2}\.\d{1,2}\.?\s*(?:20\d{2})?", re.I),
        re.compile(r"gültig\s+bis\s+.{1,20}", re.I),
        re.compile(r"aktion\s+endet", re.I),
    ],
    "flash": [
        re.compile(r"kurzzeitig", re.I),
        re.compile(r"flash\s*sale", re.I),
        re.compile(r"blitz(angebot|deal)", re.I),
        re.compile(r"schnell\s+zugreifen", re.I),
        re.compile(r"so\s+lange\s+der\s+Vorrat\s+reicht", re.I),
        re.compile(r"solange\s+der\s+Vorrat\s+reicht", re.I),
    ],
}


def detect_urgency(title: str, description: Optional[str] = None) -> dict:
    """
    Detect urgency signals in deal text.

    Args:
        title: Deal title (required)
        description: Deal description/body (optional)

    Returns:
        dict with:
        - level: "none" | "low" | "medium" | "high" | "critical"
        - score: 0-10 urgency score
        - signals: list of detected signal types
        - details: list of matched phrases with type
    """
    text = title or ""
    if description:
        text += " " + description

    signals = []
    details = []
    score = 0.0

    for category, patterns in _PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                signals.append(category)
                details.append({
                    "type": category,
                    "match": match.group(0).strip(),
                    "span": match.span(),
                })

                # Score weights
                if category == "stock_low":
                    score += 8.0
                    # Extract count for refinement
                    count = int(match.group(1)) if match.lastindex and match.group(1).isdigit() else 99
                    if count <= 3:
                        score += 2.0  # very low stock
                elif category == "stock_phrase":
                    score += 5.0
                elif category == "time_limited":
                    score += 4.0
                elif category == "flash":
                    score += 6.0

    # Cap score
    score = min(10.0, score)

    # Determine level
    if score >= 10:
        level = "critical"
    elif score >= 7:
        level = "high"
    elif score >= 4:
        level = "medium"
    elif score >= 1:
        level = "low"
    else:
        level = "none"

    return {
        "level": level,
        "score": round(score, 1),
        "signals": list(set(signals)),
        "details": details,
    }


def urgency_weight(level: str) -> float:
    """Convert urgency level to a weight multiplier for alert prioritization."""
    weights = {
        "critical": 2.0,
        "high": 1.5,
        "medium": 1.2,
        "low": 1.0,
        "none": 1.0,
    }
    return weights.get(level, 1.0)


def format_urgency(urgency: dict) -> str:
    """Format urgency as a compact string for alerts."""
    icons = {
        "critical": "🚨",
        "high": "⚡",
        "medium": "⏰",
        "low": "",
        "none": "",
    }
    icon = icons.get(urgency["level"], "")
    if urgency["level"] in ("low", "none"):
        return ""
    return f"{icon} {urgency['level'].upper()} urgency (score: {urgency['score']}/10)"
