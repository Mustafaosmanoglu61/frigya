# 📂 Frigya — Ekip Operasyon Akışı Dokümantasyonu

Bu klasör, Frigya üzerinde **AI-destekli geliştirme iş akışını** 3 gerçek vaka
üzerinden anlatan doküman setidir. Board'dan PBI kapanışına kadar bir bug/bulgu'nun
nasıl yolculuk ettiğini somut artefaktlarla gösterir.

> **Not:** 3 vaka (BUG-001, FEAT-002, UI-003) **kasıtlı olarak açık** bırakılmıştır
> — sunumun canlı demo materyalidir. Kod değiştirilmemiştir.

---

## 🗺️ Önce Ne Okunmalı?

| Sıra | Dosya | Kim için | Ne anlatır |
|---|---|---|---|
| 1 | **`00-PRESENTATION.md`** | Herkes (sunum) | Ana anlatı — pipeline, roller, 3 vaka, metrikler |
| 2 | `05-meeting-runbook.md` | Mustafa (sunan) | Dakika dakika kim ne zaman konuşur + demo scripti |
| 3 | `06-developer-playbook.md` | Emine, Ayşe | Azure Work Item'dan test deployment'a dev'in 8 adımı |
| 4 | `07-dilara-testops.md` | Dilara | Azure MCP ile tek artifact + G4 gate (iki bilgi şart) + Faz 5 |
| 5 | `04-checkpoints.md` | Dilara, Mustafa | 5 faz + 5 kalite geçidi + RACI matrisi |
| 6 | `01-board-input/` | Şevval, Board | Azure Work Item'ın makine-okunur hali |
| 7 | `02-test-scenarios/` | Şevval, Dilara | Board'dan üretilen Given/When/Then senaryolar |
| 8 | `03-dev-solutions/` | Emine, Ayşe | `*.solution.md` (girdi) · `*.ai-session.md` (AI oturum izi) · `*.dev-summary.md` (çıktı) |

---

## 🔄 Akışın Özeti

```
 Azure Board        🤖 AI Generator       👩‍💻 Dev + AI tool        🚀 Dilara
 (tek kaynak)            │                      │                      │
 Work Item ─ G1 ▶ scenarios.yaml ─ G2 ▶ solution.md (girdi)            │
 (neden+kabul)    (given/when/then        │                            │
                   +repo_anchors)         ▼ kodla + commit AB#1234     │
                                     dev-summary.md (çıktı) ─ G3 ─▶ G4 ─┤
                                     (selector+fixture)               ▼
                                                          Faz 5: Test Deployment
                                                          Playwright MCP + Azure
                                                          test + repo fixtures
                                                                 │ G5 (Mustafa)
                                                                 ▼
                                                          Work Item → Closed
```

Gate detayları: [`04-checkpoints.md`](04-checkpoints.md) ·
Developer adımları: [`06-developer-playbook.md`](06-developer-playbook.md) ·
Dilara TestOps (Azure MCP + gate): [`07-dilara-testops.md`](07-dilara-testops.md)

> **🚦 Kritik gate kuralı:** Developer AI veya manuel — fark etmez; ama
> **(A) ne değişti+selector** ve **(B) Dev Summary** bilgileri Work Item'da
> olmadan Dilara test deployment'a **başlamaz** (G4 bounce-back). Board referans.

---

## 🎬 Bu Sprintteki 3 Vaka

| Story | Tür | Discovery | Sayfa | Assignee |
|---|---|---|---|---|
| **BUG-001** | 🐛 Bug (P1) | Şevval (top-down) | `/islemler` satış filtresi | Emine |
| **FEAT-002** | ✨ Enhancement (P2) | Şevval (top-down) | `/pozisyonlar` günlük % | Ayşe |
| **UI-003** | 🎨 UI (P3) | Ayşe (bottom-up) | `/pozisyonlar` unrealized etiketi | Ayşe |

Her vaka için artefakt zinciri:
`01-board-input/` → `02-test-scenarios/` → `03-dev-solutions/*.solution.md`
(dev'e girdi) → `03-dev-solutions/*.dev-summary.md` (dev çıktısı → Dilara hand-off)

---

## 👥 Takım

| Kişi | Rol |
|---|---|
| **Şevval** | Product + Test management (board açar, senaryo onaylar) |
| **Emine** | Backend/JS dev |
| **Ayşe** | UI dev |
| **Mustafa** | Test Manager (sunan + final approver) |
| **Dilara** | QA DevOps (pipeline orkestratörü) |

---

## 🛠️ Sunumu Slayt Olarak Açma (opsiyonel)

`00-PRESENTATION.md` Marp uyumlu yazıldı:

```bash
# PDF'e çevir
npx @marp-team/marp-cli docs/workflow/00-PRESENTATION.md --pdf

# Canlı izle (watch)
npx @marp-team/marp-cli docs/workflow/00-PRESENTATION.md -p
```

GitHub'da da düz markdown olarak okunabilir (slayt ayraçları `---` görünür).
