# 🚀 Dilara TestOps — Azure MCP ile Hand-off → Test Deployment

> **Faz 4 (Hand-off) + Faz 5 (Test Deployment) sahibi: Dilara (QA DevOps).**
> Dilara işleri **ayrı ayrı toplamaz** — Azure MCP ile board'dan tek seferde
> çeker, **tek konsolide artifact** oluşturur, üzerine yorum yapar ve gate
> kararını verir. Board = tek referans noktası.

---

## 🧲 Adım 1 — Azure MCP ile Board'dan Çek (tek hamle)

Dilara, Work Item'ı (`AB#1234`) Azure MCP üzerinden çeker. Tek çağrı ile
Work Item + bağlı **artefaktlar** + **commit/PR** + **dev notları** gelir:

```
Azure MCP: getWorkItem(AB#1234, expand=relations,attachments,comments)
   ├─ alanlar: state, acceptance criteria
   ├─ attachments: solution.md, scenarios.yaml, dev-summary.md / ai-session.md
   ├─ linked PR: !187 (branch bugfix/AB1234-...)
   └─ commits: a1b2c3d ("... AB#1234")
```

Bunları **tek konsolide artifact**'a indirir (örn. `handoff/AB1234.bundle.md`):
board özeti + dev çıktısı + test senaryoları + commit referansı tek yerde.

---

## 🚦 Adım 2 — Gate Kontrolü (G4): İKİ BİLGİ ŞART

Dilara test deployment'a **yalnızca** iki bilgi de varsa geçer:

| # | Gerekli bilgi | AI yolu | Manuel yol |
|---|---|---|---|
| **A** | **Ne değişti + nerede** (anchor/dosya + selector'lar) | `ai-session.md` (diff) | Work Item **resolution notu** (elle yazılmış değişiklik + selector) |
| **B** | **Dev Work Summary** (fixture ihtiyacı + risk + doğrulama) | `dev-summary.md` | Work Item yorumu (aynı başlıklar elle) |

> **Developer her zaman AI kullanmaz.** Bazen değişikliği elle yazıp Work Item'a
> resolution notu bırakır — sorun değil. **Önemli olan format değil, iki bilginin
> de bulunması.** Biri eksikse Dilara **başlamaz**.

### ⛔ Bounce-back (geri dönüş) kuralı
```
A var, B yok  → Dilara: "Dev Summary eksik — fixture/selector bilinmiyor,
                 test deploy edemem." → Work Item: Active'e geri, dev'e atanır.
A yok, B var  → "Değişiklik kapsamı/selector belirsiz." → geri dönüş.
İkisi de yok  → Gate hiç açılmaz, Work Item Resolved'a alınamaz.
```

Dilara bu kararı **konsolide artifact üzerine yorum** olarak yazar (iz kalır):
> _"G4 RED — `dev-summary` yok. Hangi portföy/fixture gerektiği belirsiz,
> selector listesi eksik. Active → Emine. (Azure MCP comment, 2026-06-01)"_

---

## 🧪 Adım 3 — Test Deployment (Faz 5, G5)

İki bilgi de tamam → Dilara konsolide artifact'tan deployment'ı kurar:

```
dev-summary.md (fixture + selector)        scenarios.yaml (given/when/then)
        │                                          │
        └──────────────┬───────────────────────────┘
                       ▼
          Playwright MCP → spec üret/güncelle
          tests/bug-001-totals-respect-filter.spec.ts
                       │
   repo fixtures ──────┤  (seed: GeneralMu/2026/8 ASTX · storageState auth · mock yok)
   Azure'da store ─────┤  (Test Plans / repo tests/)
                       ▼
          Azure Pipeline (CI) → koş
                       │
                yeşil ▼            kırmızı ▼
        Work Item → Closed     bounce-back → dev
        (G5, Mustafa onayı)    (artifact'a fail log yorumu)
```

- **Selector'lar** dev-summary'den → spec doğrudan hedefler (keşif yok).
- **Fixture** dev-summary'den → seed/auth/mock deploy edilir.
- **scenarios.yaml** → Playwright MCP spec'i üretir/günceller.
- Yeşil → `Fixes AB#1234` zaten PR'da → Work Item **Closed**.

---

## 📌 Neden Tek Konsolide Artifact?

| Ayrı ayrı toplamak | Azure MCP + tek artifact |
|---|---|
| Solution, summary, commit, senaryo dağınık | Hepsi `AB1234.bundle.md`'de |
| "Hangi versiyon güncel?" karışıklığı | Board tek referans → tek çekim |
| Yorum/karar izi farklı yerlerde | Tek artifact üzerine tek yorum akışı |
| Gate kararı belgesiz | Bounce-back yorumu artifact'ta, izlenebilir |

> Board referans noktası; Dilara'nın artifact'ı onun **anlık görüntüsü** (snapshot).

---

## ✅ Dilara Checklist
- [ ] Azure MCP ile Work Item + ekler + PR + commit çekildi
- [ ] Konsolide artifact oluşturuldu (`handoff/AB####.bundle.md`)
- [ ] **G4:** A (değişiklik+selector) **ve** B (dev-summary) var mı? → yoksa bounce-back yorumu
- [ ] Playwright MCP spec üretildi/güncellendi
- [ ] Repo fixtures + auth + (gerekiyorsa) mock deploy
- [ ] Azure Pipeline yeşil → Mustafa G5 onayı → Work Item Closed
