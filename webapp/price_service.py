"""
Price Service — SOLID mimarisi ile fiyat veri sağlama modülü.

Genişletme:
    class FinnhubProvider(PriceProvider):
        def __init__(self, api_key: str): ...
        def get_prices(self, symbols): ...

    # Kullanım (mevcut kod değişmez):
    get_prices(symbols, provider=FinnhubProvider(api_key="xxx"))
"""
from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from typing import Optional

warnings.filterwarnings("ignore", category=Warning)


# ─── Interface ───────────────────────────────────────────────────────────────

class PriceProvider(ABC):
    """Soyut fiyat sağlayıcı arayüzü."""

    @abstractmethod
    def get_prices(self, symbols: list[str]) -> dict[str, dict]:
        """
        Her sembol için fiyat bilgisini döndürür.

        Returns:
            {
              "AAPL": {
                "current_price": 175.5,
                "prev_close":    173.2,
                "change_pct":    1.33,   # % (prev_close'a göre)
                "market_state":  "REGULAR" | "PRE" | "POST" | "CLOSED" | None,
                "currency":      "USD",
                "error":         None,   # veya hata mesajı
              },
              ...
            }
        """


# ─── Implementasyonlar ────────────────────────────────────────────────────────

class YFinanceProvider(PriceProvider):
    """Yahoo Finance üzerinden fiyat çeken provider (ücretsiz, API key gerektirmez)."""

    def get_prices(self, symbols: list[str]) -> dict[str, dict]:
        import yfinance as yf

        unique = list({s.upper() for s in symbols if s.strip()})
        if not unique:
            return {}

        try:
            tickers = yf.Tickers(" ".join(unique))
        except Exception as e:
            return {s: {"current_price": None, "error": f"Batch init hatası: {e}"} for s in unique}

        results: dict[str, dict] = {}
        for sym in unique:
            try:
                ticker_obj = tickers.tickers[sym]
                fi = ticker_obj.fast_info
                cur  = fi.last_price
                prev = fi.previous_close
                chg  = ((cur - prev) / prev * 100) if (prev and prev > 0) else None

                # Extended hours: ticker.info'dan al (fast_info'da yok)
                ext_price = None
                ext_change_pct = None
                try:
                    info = ticker_obj.info
                    post_price = info.get("postMarketPrice")
                    pre_price  = info.get("preMarketPrice")
                    ext_price  = post_price or pre_price

                    post_chg = info.get("postMarketChangePercent")
                    pre_chg  = info.get("preMarketChangePercent")
                    ext_change_pct = post_chg if post_price else pre_chg
                except Exception:
                    pass

                results[sym] = {
                    "current_price": round(cur, 4)  if cur  is not None else None,
                    "prev_close":    round(prev, 4) if prev is not None else None,
                    "change_pct":    round(chg, 2)  if chg  is not None else None,
                    "market_state":  getattr(fi, "market_state", None),
                    "currency":      getattr(fi, "currency", "USD"),
                    "extended_hours_price": round(ext_price, 4) if ext_price is not None else None,
                    "extended_hours_change_pct": round(ext_change_pct, 2) if ext_change_pct is not None else None,
                    "error":         None,
                }
            except Exception as e:
                results[sym] = {
                    "current_price": None,
                    "prev_close":    None,
                    "change_pct":    None,
                    "market_state":  None,
                    "currency":      "USD",
                    "extended_hours_price": None,
                    "extended_hours_change_pct": None,
                    "error":         str(e),
                }

        return results


# ─── Public API ───────────────────────────────────────────────────────────────

_default_provider: PriceProvider = YFinanceProvider()


def get_prices(
    symbols: list[str],
    provider: Optional[PriceProvider] = None,
) -> dict[str, dict]:
    """
    Stateless fiyat sorgulama — DB bağımlılığı YOK.

    Args:
        symbols:  Sembol listesi (büyük/küçük harf fark etmez)
        provider: Opsiyonel override; None ise YFinanceProvider kullanılır

    Returns:
        symbol → fiyat dict (bkz. PriceProvider.get_prices docstring)
    """
    if not symbols:
        return {}
    return (provider or _default_provider).get_prices(symbols)


# ─── Historical Data ──────────────────────────────────────────────────────

def get_historical_data(symbol: str, interval: str = "1d") -> list[dict]:
    """
    Historical OHLCV verisi yfinance'ten.

    Args:
        symbol:   Sembol (örn: AAPL)
        interval: "1d" (günlük), "1h" (saatlik), vb.

    Returns:
        [
          {"date": "2026-04-10", "open": 175.5, "high": 176.2, "low": 175.0, "close": 175.8, "volume": 1000000},
          ...
        ]
    """
    import yfinance as yf
    from datetime import datetime, timedelta

    symbol = symbol.upper().strip()
    if not symbol:
        return []

    try:
        # Veri dönemi: interval'e göre
        if interval == "1d":
            # Son 6 ay günlük veri
            start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        elif interval == "1h":
            # Son 1 ay saatlik veri
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        else:
            # Default: son 3 ay
            start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start, interval=interval)

        if df.empty:
            return []

        # DataFrame → list[dict]
        result = []
        for idx, row in df.iterrows():
            result.append({
                "date": idx.strftime("%Y-%m-%d %H:%M" if interval != "1d" else "%Y-%m-%d"),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]) if "Volume" in row else 0,
            })

        return result
    except Exception as e:
        return []
