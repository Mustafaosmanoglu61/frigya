"""
frigya_core.notes — symbol_notes/portfolio_notes metinlerinden seviye/earnings/tez ayıklar.

(skill not_parser.py'den birebir port; saf fonksiyonlar, yan etki yok.)
"""
import re


RX_STOP = re.compile(
    r"(?:^|[^a-zA-Z])(?:stop|zarar)\s*(?:fiyatı?|seviyesi?|bölgesi?)?\s*[:=]?\s*\$?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
RX_STOP_ALT = re.compile(
    r"\$?(\d+(?:[.,]\d+)?)\s*(?:altı|altına?|altında)\s*(?:stop|zarar)",
    re.IGNORECASE,
)
RX_TABAN = re.compile(
    r"(?:taban|destek|alım\s*bölgesi)\s*\(?\s*\$?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
RX_HEDEF_TEK = re.compile(
    r"(?:hedef|target)\s*(?:fiyatı?|seviyesi?)?\s*[:=]?\s*\$?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
RX_HEDEF_RANGE = re.compile(
    r"\$?(\d+(?:[.,]\d+)?)\s*[-–]\s*\$?(\d+(?:[.,]\d+)?)\s*(?:direnç|hedef|target|aralı[ğg]ı?)",
    re.IGNORECASE,
)
RX_DIRENC = re.compile(
    r"(?:direnç|resistance)\s*(?:seviyesi?|noktası?)?\s*[:=]?\s*\$?\s*(\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)

EARNINGS_KW = re.compile(
    r"\b(earnings|bilanço|EPS|beat|miss|guidance|kazan[çc]|ex[-\s]?dividend|temettü)\b",
    re.IGNORECASE,
)
EARNINGS_DATE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Oca|Şub|Mar|Nis|May|Haz|Tem|Ağu|Eyl|Eki|Kas|Ara)\w*\s+\d{4}?)",
    re.IGNORECASE,
)

THESIS_KW = re.compile(
    r"\b(kırılım|breakout|sıkışma|breakdown|tepki|reversal|destek\s+test|direnç\s+test"
    r"|trend\s+dönüşü|alım\s+fırsatı|satım\s+sinyali|FOMO|panic)\b",
    re.IGNORECASE,
)

MACRO_PEOPLE = re.compile(
    r"\b(Tunç\s+Şat[ıi]roğlu|Cuma\s+Çevik|Şat[ıi]roğlu|Çevik|Bölüm\s*\d+)",
    re.IGNORECASE,
)
MACRO_CONCEPT = re.compile(
    r"\b(FED|CPI|PPI|NFP|faiz|inflation|enflasyon|istihdam|GDP|jeopolitik|IPO|halka\s+arz)\b",
    re.IGNORECASE,
)


def to_float(s):
    if s is None:
        return None
    return float(s.replace(",", "."))


def parse_note(text):
    """Tek not metnini parse et → {levels, earnings, thesis, macro, has_image}."""
    if not text:
        return {"levels": {}, "earnings": None, "thesis": [], "macro": [], "has_image": False}

    out = {
        "levels": {},
        "earnings": None,
        "thesis": [],
        "macro": [],
        "has_image": "[GÖRSEL]" in text or "[resim]" in text.lower(),
    }

    m = RX_STOP.search(text) or RX_STOP_ALT.search(text)
    if m:
        out["levels"]["stop"] = to_float(m.group(1))

    m = RX_TABAN.search(text)
    if m:
        out["levels"]["taban"] = to_float(m.group(1))

    m = RX_HEDEF_RANGE.search(text)
    if m:
        v1, v2 = to_float(m.group(1)), to_float(m.group(2))
        out["levels"]["hedef_min"] = min(v1, v2)
        out["levels"]["hedef_max"] = max(v1, v2)
    else:
        m = RX_HEDEF_TEK.search(text)
        if m:
            out["levels"]["hedef"] = to_float(m.group(1))

    m = RX_DIRENC.search(text)
    if m and "direnc" not in out["levels"]:
        out["levels"]["direnc"] = to_float(m.group(1))

    if EARNINGS_KW.search(text):
        date_m = EARNINGS_DATE.search(text)
        out["earnings"] = {
            "mentioned": True,
            "date_hint": date_m.group(1) if date_m else None,
            "snippet": text[max(0, (EARNINGS_KW.search(text)).start() - 30):
                            (EARNINGS_KW.search(text)).end() + 60].strip(),
        }

    for m in THESIS_KW.finditer(text):
        out["thesis"].append(m.group(1).lower())
    out["thesis"] = list(set(out["thesis"]))

    for m in MACRO_PEOPLE.finditer(text):
        out["macro"].append({"type": "person", "name": m.group(1)})
    for m in MACRO_CONCEPT.finditer(text):
        out["macro"].append({"type": "concept", "name": m.group(1).upper()})

    return out


def parse_notes_list(notes):
    """Not listesi → birleşik overlay (en yeni seviye kazanır) + earnings/tez/makro."""
    parsed = []
    for n in notes:
        text = n.get("note") or n.get("note_text") or n.get("text") or n.get("note_plain") or ""
        p = parse_note(text)
        parsed.append({
            "created_at": n.get("created_at") or n.get("added_at"),
            "portfolio": n.get("portfolio"),
            "text_excerpt": text[:200],
            "parsed": p,
        })
    levels_overlay = {}
    earnings_latest = None
    macro_all = []
    thesis_all = []
    for p in reversed(parsed):  # eski → yeni; en yeni üste biner
        for k, v in p["parsed"]["levels"].items():
            levels_overlay[k] = v
        if p["parsed"].get("earnings"):
            earnings_latest = p["parsed"]["earnings"]
        macro_all.extend(p["parsed"]["macro"])
        thesis_all.extend(p["parsed"]["thesis"])

    return {
        "notes_parsed": parsed,
        "levels_from_notes": levels_overlay,
        "latest_earnings_hint": earnings_latest,
        "thesis_keywords": list(set(thesis_all)),
        "macro_mentions": macro_all,
    }
