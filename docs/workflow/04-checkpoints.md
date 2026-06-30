# 🚦 Kalite Geçitleri (Checkpoints) & RACI

> **Tek girdi kaynağı: Azure Boards.** Bir Work Item (Bug/PBI) board'a
> düştüğü andan Closed olana kadar **5 fazdan** ve **5 kapıdan** geçer.
> Her kapıda bir sorumlu, bir kontrol kriteri ve "geçemezse ne olur" kuralı var.
> Pipeline bu kapılarda durup onay alır — hiçbir aşama sessizce atlanmaz.

---

## 5 Faz & Akış Şeması

```
 FAZ 1      FAZ 2        FAZ 3          FAZ 4         FAZ 5
 Azure     Senaryo     Geliştirme     Hand-off    Test Deployment
 Board    (Azure'da)     (Dev)        → Dilara    (Playwright MCP)
   │          │            │             │              │
   ▼          ▼            ▼             ▼              ▼
  G1 ───────▶ G2 ───────▶ G3 ─────────▶ G4 ──────────▶ G5
 Şevval     Şevval    Dev (self)      Dilara         Mustafa
                      + Dev Summary                  → PBI Closed
```

---

## Geçitler

| Gate | Adı | Sorumlu | Ne kontrol edilir | Geçemezse |
|------|-----|---------|-------------------|-----------|
| **G1** | Board Onayı | Şevval | `amac` + `kabul_kriterleri` net, `beklenen` ölçülebilir, ekran kanıtı var | Board'a geri → reporter netleştirir |
| **G2** | Senaryo Onayı | Şevval | happy + edge + negative kapsanmış, `repo_anchors` dolu, assertion'lar deterministik | Generator yeniden / elle düzeltilir |
| **G3** | Dev Tamam | Dev (self-check) | kod + commit (AB#id linkli) + **Dev Work Summary** hazır, lokal smoke geçti | Dev devam eder, hand-off açılmaz |
| **G4** | Hand-off Kabul | Dilara | Dev Summary'de selector'lar + fixture ihtiyacı + branch/PR eksiksiz | Dev'e geri → summary tamamlanır |
| **G5** | Test Deployment | Mustafa | Playwright MCP spec'leri Azure'da koştu yeşil + fixture deploy oldu + traceability tam → **Work Item Closed** | Pipeline kırmızı → dev'e döner |

---

## "Lazer" Prensibi — Anchor + Commit testleri yönlendirir

Pipeline'ın kalbi şu zincir:

```
Azure Work Item (kabul_kriteri)              ← tek girdi kaynağı
   └─▶ scenarios.yaml (repo_anchors + assert)        [Azure'da store]
          └─▶ solution.md (anchor + commit şablonu)  → dev'e GİRDİ
                 └─▶ commit ("... AB#1234")
                        └─▶ dev-summary.md (selector + fixture)  → dev ÇIKTI
                               └─▶ Playwright MCP spec (scenarios'tan)
                                      └─▶ Azure Pipeline run → Work Item Closed
```

Her halka bir öncekine **referansla** bağlı → bir story'nin board'dan test'e
kadar izi **tek tıkla** sürülebilir. `repo_anchors` (dosya:satır) developer'ın
AI tool'unu doğru yere "lazer gibi" yönlendirir; commit'teki `AB#1234`
linki de Work Item ↔ kod ↔ test üçgenini Azure'da otomatik kapatır.

---

## 🔁 Developer Faz 3 — Hand-off'a Ne Teslim Edilir

Faz 3 (Geliştirme) sonunda developer **iki ayrı artefakt** üretir:

| Artefakt | Yön | İçerik |
|---|---|---|
| `*.solution.md` | dev'e **GİRDİ** | nereye dokun + commit şablonu (test/product yazdı) |
| `*.dev-summary.md` | dev'den **ÇIKTI** | ne yaptım + yeni selector'lar + fixture ihtiyacı + risk |

> **Dev Work Summary**, Dilara'nın koda girmeden test deploy etmesini sağlar.
> Detay & şablon: [`06-developer-playbook.md`](06-developer-playbook.md) ·
> [`03-dev-solutions/_TEMPLATE.dev-summary.md`](03-dev-solutions/_TEMPLATE.dev-summary.md)

---

## 👥 RACI Matrisi

> **R** = Responsible (yapan) · **A** = Accountable (hesap veren/onaylayan)
> **C** = Consulted (görüşü alınan) · **I** = Informed (bilgilendirilen)

| Faz | Şevval | Emine | Ayşe | Mustafa | Dilara |
|---|:---:|:---:|:---:|:---:|:---:|
| Faz 1 · Board (G1) | **R/A** | I | I | C | I |
| Faz 2 · Senaryo (G2) | **R/A** | C | C | C | C |
| Faz 3 · Geliştirme + Dev Summary (G3) | C | **R**(kod) | **R**(UI) | I | C |
| Faz 4 · Hand-off (G4) | C | C | C | I | **R/A** |
| Faz 5 · Test Deployment (G5) | C | I | I | **A** | **R** |
| Work Item Closed | I | I | I | **R/A** | C |

---

## Bu Sprintteki 3 Vaka — Geçit Durumu (demo anı)

| Story | Discovery | Assignee | G1 | G2 | G3 | G4 | G5 |
|---|---|---|:--:|:--:|:--:|:--:|:--:|
| 🐛 BUG-001 | Şevval (top-down) | Emine | ✅ | ✅ | ⏳ | ⏳ | ⏳ |
| ✨ FEAT-002 | Şevval (top-down) | Ayşe | ✅ | ✅ | ⏳ | ⏳ | ⏳ |
| 🎨 UI-003 | Ayşe (bottom-up) | Ayşe | ✅ | ✅ | ⏳ | ⏳ | ⏳ |

> ⏳ = sunum demosunda **canlı** gösterilecek: 3 vaka da **G2'yi geçti, G3'te**
> (geliştirme) bekliyor — kod henüz yazılmadı, bug'lar tarayıcıda hâlâ açık.
> Sahnede developer + AI tool ile G3 (kod + Dev Summary) → G4 (hand-off) →
> G5 (Playwright MCP test deployment) zinciri canlı koşulur.
