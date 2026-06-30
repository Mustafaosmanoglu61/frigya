# Örnek çıktı — `frigya_sembol_analiz` + `frigya_render_markdown`

> Bu, frigya MCP'sinin Claude'a döndürdüğü gerçek bir analiz çıktısının **örnek** halidir.
> Kişisel kazanç/zarar tutarları (unrealized $, net K/Z $) bilinçli olarak çıkarılmıştır —
> amaç çıktının **biçimini ve birleştirme gücünü** göstermektir, gerçek portföy verisini değil.

Aşağıdaki çıktı tek bir araç çağrısıyla şunları birleştirir: **kullanıcının kendi DB'si**
(pozisyon, FIFO geçmişi, hedef/stop), **Massive canlı piyasa** (fiyat, RSI/Stoch/MACD,
zirveden düşüş) ve **kullanıcının serbest metin notları** (parse edilip seviyelere çevrilir).

---

# RKLX — Frigya Analiz · 2026-06-10 02:14
*Tag: Space*
*Defiance Daily Target 2X Long RKLB ETF · XNAS · Dayanak: RKLB*

## Pozisyon
- 15 adet açık, anlık $61.36 → unrealized P&L otomatik hesaplanır _(tutar örnekten çıkarıldı)_.

## Piyasa
- Kapanış $61.36 · 60g zirve $114.83 (-46.56%) · Stoch %K 12.4 · RSI 45.4
- **Kısa vade**: Stoch 12.4 (dipte) | MACD histogram -5.72 (bearish momentum)
- **Uzun vade**: 60g zirveden -46.6%

## Tanımlı Hedef/Stop
| Portföy | Hedef | Taban | Stop |
|---|---|---|---|
| family | $50.00 | $30.00 | — |
| GeneralMu | $32.83 | $28.00 | $33.00 |
| test | $100.00 | $40.00 | — |

_[family] · hedef $50.0 (-18.5% uzak) | [GeneralMu] · stop $33.0 (+46.2% uzak) · hedef $32.83 (-46.5% uzak) | [test] · hedef $100.0 (+63.0% uzak)_

## Notlar (kullanıcının kendi yazdığı — frigya bunları seviyelere çevirir)
- _2026-06-08 (family)_: Cuma Çevik: Rocket Lab (RKLB) için 104$ ve 76$ seviyeleri en güçlü destek noktaları. Satış nedenleri: güçlü istihdam sonrası Fed faiz indirimi beklentisinin zayıflaması, SpaceX IPO öncesi likidite ihtiyacı. VIX tarihsel olarak bu tür yükselişten sonra 1 ay içinde toparlanıyor.

## Frigya geçmişi (bu sembolde)
- 12 realized trade · win rate %75 · ort. hold 9.9g · net K/Z _(kişisel — örnekten çıkarıldı)_
- ⚠ bu sembolde win rate %75, ort. hold 9.9g, win/loss oranı 1.22.

## Karar / Aksiyon
- **⚠ Dün açılan family pozisyonunun stop ve hedefi tanımsız. 2x kaldıraçlı üründe seviye tanımlanmalı.**
- ❓ Family lot için stop/hedef belirle

_Veri boşlukları: news: Massive allowlist'te haber endpoint'i yok_

---
<sub>Kaynak: frigya MCP · frigya_sembol_analiz + frigya_render_markdown · Piyasa: Massive Market Data</sub>
