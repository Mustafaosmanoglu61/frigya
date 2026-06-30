# 👩‍💻 Developer Playbook — Azure Board'dan Test Deployment'a

> **Tek girdi kaynağı: Azure Boards.** Her iş bir Work Item (Bug / PBI) olarak
> board'da başlar. Developer bu kartı "çeker" ve aşağıdaki adımları izler.
> Bu doküman, kartı çektikten sonra **gerçekte ne yapılacağını** ve
> hand-off'ta Dilara'ya **neyin teslim edileceğini** anlatır.

---

## 🗺️ Developer'ın 8 Adımı (Faz 3)

```
1. Work Item'ı çek      → Azure Board: New → Active
2. Branch aç            → bugfix/AB1234-totals-filter
3. Artefaktları oku     → board.yaml + scenarios.yaml + solution.md
4. AI tool ile uygula   → anchor'ları besle, kodu üret
5. Lokal doğrula        → lint + manuel smoke + (varsa) lokal spec
6. Commit disiplini     → AB#1234 linkli, atomik, anlamlı mesaj
7. PR aç                → Work Item'a otomatik bağlanır
8. Dev Work Summary yaz → Dilara'ya hand-off dokümanı (ÇIKTI)
```

> **Kritik ayrım:**
> `solution.md` = developer'a **GİRDİ** (nasıl çöz).
> `*.dev-summary.md` = developer'dan **ÇIKTI** (ne yaptım, test nasıl deploy edilir).

---

## 1️⃣ Work Item'ı Çek (Azure Board)

- Board'da kartı kendine ata (**Assigned To = sen**), durumu **New → Active**.
- Acceptance Criteria + ekli artefaktları gör: `board.yaml`, `scenarios.yaml`, `solution.md`.
- Kafanda netleşmeyen varsa **kart üzerinden** Şevval'e sor (Slack değil — iz kalsın).

> ⚠️ Kartta yazmayan hiçbir "ekstra iş" yapma. Scope kart = scope kod.

---

## 2️⃣ Branch Aç (isimlendirme = iz)

```
bugfix/AB1234-totals-filter        # bug
feature/AB1235-daily-pct-column    # enhancement
ui/AB1236-unrealized-prefix        # ui
```

- `AB<id>` = Azure Boards Work Item ID → branch'i karta bağlar.
- `main`'den aç, güncel `pull` ile başla.

---

## 3️⃣ Artefaktları Oku (sırayla)

| Dosya | Ne verir |
|---|---|
| `01-board-input/<id>.yaml` | **Neden** + kabul kriteri + edge case'ler |
| `02-test-scenarios/<id>.scenarios.yaml` | **Nasıl doğrulanır** + `repo_anchors` |
| `03-dev-solutions/<id>.solution.md` | **Nereye dokun** + commit şablonu |

> `repo_anchors` (dosya:satır) → AI tool'unu doğrudan oraya yönlendir.

---

## 4️⃣ AI Tool ile Uygula (anchor-driven)

`solution.md`'yi AI code tool'a (Claude Code / Cursor) **attach et**, sonra:

- **Anchor'ları ver:** "Sadece `solution.md`'deki anchor tablosundaki yerlere dokun."
- **Mevcut helper'ları kullandır:** `fmtUsd`, `_effPrice`, `fmtPct` zaten var → yeniden yazdırma.
- **Diff'i minimal tut:** ilgisiz satırları reformat etme (review gürültüsü + merge riski).
- **Pattern'i taklit ettir:** komşu kodun stilini koru (style fingerprint).

> 🤖 AI tool'u **structured artefakt** besler → tahmin marjı düşük, çıktı tutarlı.

---

## 5️⃣ Lokal Doğrulama (PR'dan önce)

```bash
# Sunucuyu çalıştır
cd webapp && uvicorn main:app --reload --port 8000

# Manuel smoke — kabul kriterini elle gör
# (BUG-001: ASTX filtrele → Net K/Z +$700.59 mi?)

# Lint / console temiz mi (tarayıcı DevTools → Console)
```

- Test spec'i bu aşamada **henüz koşturmuyorsun** — o Faz 5'te (Dilara).
- Ama `scenarios.yaml`'daki beklenen değerleri **elle** doğrula.

---

## 6️⃣ Commit Disiplini ⭐ (en kritik kısım)

### Azure Work Item linkleme
Commit mesajında **`AB#1234`** yaz → commit otomatik olarak Work Item'a bağlanır:

```
fix(islemler): make sales KPIs and TOTAL respect active filter

KPI cards and tfoot TOTAL now recalculate from visible rows on every
filter change. Server-side totals remain for initial render; new
client-side _recalcTotals() runs at the end of filterTable().

- Add data-kpi / data-toplam / data-raw / data-pnl attributes
- New _recalcTotals() sums visible rows and updates DOM
- Empty match → $0.00 KPIs, '—' success, hidden tfoot

AB#1234
```

### Commit kuralları
- **Atomik:** her commit tek bir mantıksal değişiklik (PR merge'de squash).
- **Konu satırı:** imperative, ≤72 char ("make", "add" — "made/added" değil).
- **Body = NEDEN:** kod ne yaptığını gösterir, sen neden yaptığını yaz.
- **AB#id zorunlu:** linklenmemiş commit = izlenebilirlik kopukluğu.

### Asla commit etme
`.env`, secret/token, `node_modules/`, `*.db` (SQLite), `test-results/`,
`tests/.auth/`. (`.gitignore` zaten kapsıyor — yine de kontrol et.)

---

## 7️⃣ PR Aç (Work Item'a bağlı)

- PR başlığında `AB#1234` → Work Item ↔ PR otomatik link.
- PR açıklamasında:
  - `solution.md` ve `scenarios.yaml`'a referans
  - "Kabul kriterleri nasıl karşılandı" kısa özeti
  - Manuel smoke sonucu (before/after screenshot)
- Branch policy: en az 1 reviewer (Şevval kod gözü / Mustafa onay).

---

## 8️⃣ Dev Work Summary Yaz (Dilara'ya ÇIKTI) ⭐

Bu, geliştirmenin **çıktı dokümanı** — Faz 4 hand-off'ta Dilara'nın test
deployment için ihtiyaç duyduğu her şeyi içerir. Ayrı bir `.md` olarak
Work Item'a attach edilir.

**Neden ayrı doküman?** Dilara, kodun *içine* girmeden test'i deploy
edebilmeli. Bunun için developer **test yüzeyini** açıkça ifşa eder:
yeni selector'lar, gereken veri durumu (fixture), sapma varsa nedeni.

Şablon: [`03-dev-solutions/_TEMPLATE.dev-summary.md`](03-dev-solutions/_TEMPLATE.dev-summary.md)
Örnek : [`03-dev-solutions/BUG-001.dev-summary.md`](03-dev-solutions/BUG-001.dev-summary.md)

---

## 🎯 İşini İzah Ederken Nelere Dikkat (özet)

| Konu | Kötü | İyi |
|---|---|---|
| **Commit mesajı** | "fix bug" | "fix(islemler): totals respect filter · AB#1234" |
| **PR açıklaması** | "değişiklikler" | hangi kabul kriteri nasıl karşılandı + screenshot |
| **Selector ifşası** | sessiz | "`[data-kpi=net-pnl]` ekledim → spec bunu hedefler" |
| **Fixture ihtiyacı** | "çalışıyor işte" | "GeneralMu portföyü, 2026, 60 satış (8 ASTX) gerekli" |
| **Sapma** | gizle | "solution.md'den şu noktada saptım çünkü ..." |

> Kural: **Dilara senin koduna bakmadan testi deploy edebilmeli.**
> Bunu mümkün kılan şey senin Dev Work Summary'n.

---

## 🤝 Faz 4 → Faz 5 Geçişi (Hand-off → Test Deployment)

Hand-off Dilara'ya geldiğinde elinde şunlar olur:
1. **Branch + commit'ler** (AB#id linkli)
2. **PR** (Work Item'a bağlı)
3. **Dev Work Summary** (selector'lar + fixture + risk notları)

Dilara bununla **Faz 5: Test Deployment**'ı başlatır:
- `scenarios.yaml` → **Playwright MCP** ile spec'e dönüşür / koşulur
- Spec'ler **Azure'da** (Test Plans / repo `tests/`) store edilir
- **Repo'daki fixture'lar** (seed veri, `tests/.auth`, mock'lar) devreye alınır
- **Azure Pipelines** CI'da koşar → yeşil → PBI **Closed**

> Detay: [`04-checkpoints.md`](04-checkpoints.md) (G4 → G5)
