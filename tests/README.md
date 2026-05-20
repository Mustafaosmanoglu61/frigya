# Frigya E2E Testleri — Playwright

Bu klasör Playwright tabanlı uçtan uca testler içerir.

## Hızlı Başlangıç

```bash
# Bağımlılıkları kur
npm install
npm run playwright:install        # Chromium tarayıcısı + system deps

# Sunucu zaten ayrı bir terminalde çalışıyor olmalı:
#   cd webapp && uvicorn main:app --reload --port 8000

# Testleri çalıştır
npm run test:e2e                  # baş gizli (CI uyumlu)
npm run test:e2e:headed           # tarayıcı görünür
npm run test:e2e:ui               # Playwright UI modu (interaktif)
npm run test:e2e:debug            # tek tek adımla
```

Sunucuyu otomatik başlatmak istersen:

```bash
PW_AUTO_SERVER=1 npm run test:e2e
```

## Login & Credentials

`tests/global-setup.ts` test başlamadan **bir kez** login olur ve session cookie'sini
`tests/.auth/admin.json` dosyasına yazar. Sonraki testler bunu kullanır.

Credentials kaynak öncelik sırası:
1. `FRIGYA_EMAIL` / `FRIGYA_PASSWORD` env değişkenleri
2. Proje kökündeki `.env` dosyasından `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`
3. Default `admin@tax-portfolio.local`

`tests/.auth/` gitignore'da — auth dosyası asla commit edilmez.

## Spec'ler

| Dosya | Kapsam |
|---|---|
| `dashboard-unrealized-kpi.spec.ts` | Dashboard Açık Pozisyon Gerçekleşmemiş K/Z KPI kartı (async fetch, AH override, 60s interval) |

## Senaryolar — `dashboard-unrealized-kpi.spec.ts`

1. **Kart render edilir** — header `GERÇEKLEŞMEMİŞ K/Z` görünür, sembol sayısı doğru
2. **Kâr senaryosu** — mock fiyat `$1000` × qty → net pozitif, `text-success`
3. **Zarar senaryosu** — mock fiyat `$0.01` × qty → net negatif, `text-danger`
4. **After-hours override** — `market_state=POST` + `extended_hours_price=$2000` →
   MV regular `$500` yerine `$2000`'den hesaplanır
5. **60s interval refresh** — `page.clock.fastForward(60s)` ile setInterval tetiklenir,
   ikinci fetch yapılır
6. **Defensive — fetch fail** — endpoint 500 dönerse net `—` kalır, `text-muted`
7. **Format doğrulaması** — net/profit/loss USD formatında, pct `±N.NN%` formatında

## Mock Stratejisi

`/api/fiyatlar/guncelle` endpoint'i `page.route()` ile mock'lanır → fiyatlar
deterministik olur, yfinance'a gerçek istek gitmez. Bu sayede:

- Test, gerçek piyasa fiyatlarından bağımsız (CI'da güvenilir)
- AH override gibi nadir durumlar deterministik üretilebilir
- Hızlı çalışır (yfinance latency yok)

## Açık Pozisyon Olmadığında

`distribution` boşsa kart hiç render edilmez (Jinja `{% if distribution %}` guard).
Bu durumda testler `test.skip()` ile pas geçilir — başarısız sayılmaz.

## Debugging

```bash
# Tek bir testi çalıştır
npx playwright test -g "AH override"

# Trace dosyası ile başarısız olanları incele
npx playwright show-trace test-results/.../trace.zip

# UI modu — adım adım inceleme
npm run test:e2e:ui
```
