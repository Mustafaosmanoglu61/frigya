# 🎙️ Sunum Runbook — 1 Sayfa

> **Toplam süre:** ~60 dk · **Sunan:** Mustafa (Test Manager)
> **Katılımcı:** Board, Şevval, Emine, Ayşe, Dilara
> **Açık tutulacak sekmeler:** Frigya (`/islemler?tab=satislar&yil=2026&portfolio=GeneralMu`,
> `/pozisyonlar`), `00-PRESENTATION.md`

---

## Zaman Çizelgesi

| Süre | Bölüm | Konuşan | Not |
|---|---|---|---|
| 0:00–0:05 | **Açılış** — neden buradayız, ağrı noktası | Mustafa | Slide 1-2 |
| 0:05–0:15 | **Pipeline + RACI** — 5 faz, 5 kapı, kim ne yapar | Mustafa + Dilara | Slide 3-7 |
| 0:15–0:18 | **İki giriş kapısı** — top-down vs bottom-up | Şevval | Slide 4 |
| 0:18–0:24 | **Developer Faz 3** — 8 adım + commit/Dev Summary disiplini | Emine | `06-developer-playbook.md` |
| 0:24–0:34 | **🐛 BUG-001 CANLI DEMO** (board→dev→test deployment) | Şevval → Emine → Dilara | aşağıdaki demo scripti |
| 0:34–0:40 | **✨ FEAT-002 + 🎨 UI-003 hızlı geçiş** | Ayşe | Slide — vaka 2-3 |
| 0:40–0:46 | **Kalite geçitleri + traceability** | Dilara | `04-checkpoints.md` |
| 0:46–0:52 | **Metrikler & feedback loop** | Mustafa | Slide — metrikler |
| 0:52–0:58 | **Q&A** | hepsi | — |
| 0:58–1:00 | **Sonraki adım** — pilot story ataması | Mustafa | kapanış |

---

## 🐛 BUG-001 Canlı Demo Scripti (en kritik 12 dk)

**Şevval anlatır (keşif):**
1. Tarayıcıda aç: `/islemler?tab=satislar&yil=2026&portfolio=GeneralMu`
2. Üst KPI'ları göster: Net K/Z = **-$1,413.16**, Satış Geliri = $159,292.81
3. Filtre kutusuna **`ASTX`** yaz.
4. **Bug'ı vurgula:** tablo 8 satıra düştü ✓ AMA KPI'lar + TOPLAM hâlâ **-$1,413.16** ✗
5. "ASTX aslında **+$700.59 KÂR**'da ama kullanıcı ekranda zarar görüyor → yanlış karar riski."

**Pipeline'ı göster (Şevval → Dilara):**
6. `01-board-input/BUG-001-totals-not-filtered.yaml` → board kartı (kabul kriteri: `+$700.59`)
7. `02-test-scenarios/BUG-001.scenarios.yaml` → 5 senaryo, `repo_anchors` dolu
8. `03-dev-solutions/BUG-001.solution.md` → anchor tablosu + commit şablonu

**Dev tarafı — Faz 3 (Emine + AI tool):**
9. `BUG-001.solution.md`'yi AI code tool'a (Claude Code / Cursor) **attach** et.
10. Tool anchor'lara gider, `_recalcTotals()` ekler — sahnede ya canlı yazdır ya hazır PR göster.
11. Commit: `fix(islemler): totals respect filter · AB#1234` → Work Item'a bağlandı.
12. **Dev Work Summary** göster (`BUG-001.dev-summary.md`): yeni selector'lar + fixture ihtiyacı.

**Hand-off → Faz 5 (Dilara, Test Deployment):**
13. Dilara **Azure MCP** ile Work Item'ı çeker → tek konsolide artifact (`AB1234.bundle.md`).
14. **G4 gate:** (A) ai-session/resolution + (B) dev-summary var mı? → varsa geç, yoksa bounce-back yorumu.
15. `scenarios.yaml` + **Playwright MCP** → spec; repo fixture'ları (GeneralMu/2026, auth) deploy.
16. Azure Pipeline yeşil → filtreyi tekrar dene → ASTX `+$700.59` ✓ → Work Item **Closed**.

**Kapanış vurgusu:** "Azure Work Item'dan test deployment'a kadar her adım izlenebilir;
commit `AB#1234` ile Work Item'a, Dev Summary ile fixture/selector'a bağlandı."

---

## Demo Güvenlik Ağı (bir şey ters giderse)
- Canlı kod yazımı takılırsa → hazır "before/after" screenshot'a geç.
- Test çalışmazsa → `BUG-001.scenarios.yaml`'daki beklenen değerleri oku, "spec bunu doğrular" de.
- İnternet/fiyat API'si gerekmez (BUG-001 server-render veri, mock yok).

---

## Anahtar Mesajlar (her fırsatta tekrarla)
- 🎯 **Niyet > mekanik:** board "neden"i, anchor "nerede"yi, test "nasıl doğrulanır"ı söyler.
- 🔗 **Traceability:** Azure Work Item → senaryo → solution → commit (AB#) → dev-summary → MCP test → Closed.
- 📤 **Dev Summary:** Dilara koda girmeden test deploy edebilmeli — selector + fixture ifşası.
- 🤖 **AI tool'u besleyen biziz:** structured artefakt = deterministik çıktı.
- 🚦 **Hiçbir kapı atlanmaz:** disiplin insanda değil, pipeline'da.
- 🚀 **Faz 5 = Test Deployment:** Playwright MCP + Azure test store + repo fixtures + CI.
