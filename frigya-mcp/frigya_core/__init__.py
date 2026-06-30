"""
frigya_core — Frigya portföy analiz çekirdeği (importable, subprocess-free).

Servis (MCP server / webapp ai.py) bu paketi import eder; DB'ye burası erişir.
Tek hakikat kaynağı (SSOT).

Public API:
  open_conn(db_path=None, user_id=None) -> (conn, path, user_id)
  build_sentez(symbol, portfolio=None, market=None, ...) -> dict   # ana orkestratör
  sembol_data(conn, user_id, symbol, portfolio=None) -> dict
  portfoy_data(conn, user_id, portfolio=None) -> dict
  davranis_data(conn, user_id, portfolio=None, year=None) -> dict
  render_markdown(sentez_dict) -> str
  render_html(sentez_dict) -> str
  hedef_guncelle(conn, user_id, symbol, portfolio, ...) -> dict
  analist_hedef(conn, user_id, symbol, portfolio, ...) -> dict
  normalize_teknik / normalize_haber / normalize_meta   # Massive passthrough şekillendirici
  parse_note / parse_notes_list                          # not ayıklama
"""
from .config import open_conn, find_db_path, detect_user_id
from .db import sembol_data, portfoy_data
from .davranis import davranis_data
from .sentez import build_sentez
from .render import render_markdown, render_html
from .yazma import hedef_guncelle, analist_hedef
from .massive import (
    normalize_teknik, normalize_haber, normalize_meta,
    teknik_from_json, haber_from_json, meta_from_json,
)
from .massive_fetch import fetch_market
from .notes import parse_note, parse_notes_list

__all__ = [
    "open_conn", "find_db_path", "detect_user_id",
    "sembol_data", "portfoy_data", "davranis_data",
    "build_sentez", "render_markdown", "render_html",
    "hedef_guncelle", "analist_hedef",
    "normalize_teknik", "normalize_haber", "normalize_meta",
    "teknik_from_json", "haber_from_json", "meta_from_json",
    "fetch_market",
    "parse_note", "parse_notes_list",
]

__version__ = "0.1.0"
