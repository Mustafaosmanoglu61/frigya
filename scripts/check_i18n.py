#!/usr/bin/env python3
"""İngilizce çevirisi eksik metinleri bulur (şablon tr(), JS _t(), router i18n.tx).

Çalıştırma: python3 scripts/check_i18n.py
Eksik varsa listeler ve 1 ile çıkar. Karşılıkları webapp/i18n.py TRANSLATIONS'a eklenir.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "webapp"))
import i18n  # noqa: E402

LITERAL = r"""(['"])((?:\\.|(?!\1).)*)\1"""
PATTERNS = {
    ".html": [rf"\btr\(\s*{LITERAL}", rf"\b_t\(\s*{LITERAL}"],
    ".js": [rf"\b_t\(\s*{LITERAL}"],
    ".py": [rf"\bi18n\.tx(?:_q)?\(\s*request,\s*{LITERAL}"],
}
# Çeviri anahtarı olmayan, değişkenden gelen veya yerinde üretilen ifadeler
FILES = [
    *sorted((ROOT / "webapp" / "templates").glob("*.html")),
    *sorted((ROOT / "webapp" / "static" / "js").glob("*.js")),
    *sorted((ROOT / "webapp" / "routers").glob("*.py")),
    ROOT / "webapp" / "main.py",
    ROOT / "webapp" / "auth_service.py",
]


def unescape(text: str) -> str:
    return text.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")


def main() -> int:
    missing = {}
    for path in FILES:
        src = path.read_text(encoding="utf-8")
        for pattern in PATTERNS[path.suffix]:
            for m in re.finditer(pattern, src, flags=re.S):
                key = unescape(m.group(2))
                if key not in i18n.TRANSLATIONS:
                    missing.setdefault(key, set()).add(path.name)
    if not missing:
        print(f"Tamam: sözlükte {len(i18n.TRANSLATIONS)} anahtar, eksik yok.")
        return 0
    print(f"{len(missing)} metnin İngilizcesi eksik:")
    for key in sorted(missing):
        print(f"  {key!r}  ({', '.join(sorted(missing[key]))})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
