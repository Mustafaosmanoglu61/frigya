---
marp: true
theme: default
paginate: true
header: "Frigya · AI-Destekli Geliştirme Akışı"
footer: "Mustafa (Test Manager) · 2026-06-01"
---

<!-- _class: lead -->
<!-- _paginate: false -->

# Frigya Geliştirme Akışı
## Board → Product → Test → Dev → Run

Bir bug/bulgu'nun yolculuğu — **3 gerçek vaka** üzerinden

**Sunan:** Mustafa (Test Manager)
**Audience:** Board · Şevval (Product/Test) · Emine + Ayşe (Dev) · Dilara (QA DevOps)

---

## 📌 Bugün Ne Konuşacağız

1. **Ağrı noktası** — neden yeni bir akışa ihtiyacımız var
2. **5 fazlı pipeline** — Board ⇄ Product ⇄ Test ⇄ Dev ⇄ Run
3. **İki giriş kapısı** — bug nereden doğar (top-down / bottom-up)
4. **Roller** — kim neyden sorumlu (RACI)
5. **3 gerçek vaka — canlı walkthrough**
   - 🐛 BUG-001 · ✨ FEAT-002 · 🎨 UI-003
6. **Kalite geçitleri** — nerede durup onay alıyoruz
7. **Metrikler & sürekli iyileştirme**

---

## 😖 Bugünkü Ağrı Noktası

Geleneksel akışta ne oluyor?

- Bug "ağızdan ağıza" anlatılıyor → herkes farklı anlıyor
- Test senaryosu **kafalarda**, dokümante değil → tekrar üretilemiyor
- Dev "neyi nerede değiştireceğini" baştan keşfediyor → zaman kaybı
- AI code tool'a **dağınık prompt** → tahmin marjı yüksek, çıktı tutarsız
- "Bu bug nasıl çözülmüştü?" → 3 ay sonra kimse hatırlamıyor

> **Sonuç:** disiplin kişilere bağlı → kişi değişince kalite düşüyor.

---

## 💡 Çözüm: Disiplin Kişide Değil, Pipeline'da

Her aşama **yapılandırılmış bir artefakt** üretir:

| Aşama | Artefakt | Format |
|---|---|---|
| Azure Board | Work Item | board kart + `*.yaml` (8 zorunlu alan) |
| Test | senaryo | `*.scenarios.yaml` (Given/When/Then) |
| Dev (girdi) | çözüm rehberi | `*.solution.md` (anchor + commit) |
| Dev (çıktı) | iş özeti | `*.dev-summary.md` (selector + fixture) |
| Test Deployment | spec + log | Playwright MCP + Azure Pipeline run |

> Aynı şema → AI tool **deterministik** çıktı verir. PM, dev, AI agent **aynı dilden** konuşur.

---

## 🔄 5 Fazlı Pipeline

```
   FAZ 1        FAZ 2        FAZ 3          FAZ 4         FAZ 5
  ┌───────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────┐
  │ AZURE │─▶│ SENARYO │─▶│GELİŞTİRME│─▶│ HAND-OFF│─▶│     TEST     │
  │ BOARD │  │(Azure'da)│  │  (Dev)   │  │→ Dilara │  │  DEPLOYMENT  │
  └───────┘  └─────────┘  └──────────┘  └─────────┘  └──────────────┘
     G1          G2            G3            G4            G5
   Şevval      Şevval     Dev(self)+      Dilara       Mustafa →
                          Dev Summary                  Work Item Closed
```

- **Tek girdi kaynağı = Azure Boards** (Work Item: Bug/PBI)
- **Faz 5 = Test Deployment:** Playwright MCP + Azure'da store edilen testler + repo fixture'ları
- Her ok bir **kalite kapısından** (Gate) geçer — sessiz geçiş yok

---

## 🗺️ Uçtan Uca Workflow Haritası

```
        ┌─────────────────────── AZURE BOARDS (tek referans) ───────────────────────┐
        │                                                                            │
  ┌─────▼─────┐   ┌──────────┐   ┌───────────────────────────┐   ┌────────────────┐ │
  │  FAZ 1    │   │  FAZ 2   │   │          FAZ 3            │   │     FAZ 4      │ │
  │  Board    │──▶│ Senaryo  │──▶│       Geliştirme          │──▶│   Hand-off     │ │
  │ Work Item │ G1│(Azure'da)│ G2│   ┌─────────┬─────────┐   │ G3│  (Dilara,      │ │
  │ Şevval    │   │ Şevval   │   │   │ AI yolu │ Manuel  │   │   │   Azure MCP)   │ │
  └───────────┘   └──────────┘   │   │ .md'ler │ resol.  │   │   └───────┬────────┘ │
        ▲                        │   └─────────┴─────────┘   │           │ G4       │
        │ bounce-back            │   ÇIKTI: (A) değişiklik+   │           │          │
        │ (kabul/senaryo eksik)  │   selector  (B) dev-summary│     iki bilgi?      │
        │                        └───────────────────────────┘     ┌─────┴─────┐    │
        │                                                          yok│        │var   │
        │◀───────────── bounce-back (A veya B eksik) ─────────────────┘        ▼      │
        │                                                            ┌────────────────┐│
        │                                                            │    FAZ 5       ││
        └──────────── bounce-back (CI kırmızı) ◀─────────────────────│ Test Deployment││
                                                                     │ Playwright MCP ││
                                                                     │ +Azure test    ││
                                                                     │ +repo fixtures ││
                                                                     └───────┬────────┘│
                                                                          G5 │ yeşil   │
                                                                             ▼         │
                                                                    Work Item CLOSED ──┘
```

> Geri oklar = **bounce-back**: bir kapı geçilemezse Work Item geri döner, iz kalır.

---

## 🚪 İki Giriş Kapısı — Bug Nereden Doğar?

Bulgular **iki yönden** gelebilir:

### ⬇️ Top-down (Product/Test açar)
Şevval regresyon kontrolünde veya kullanıcı geri bildiriminden fark eder
→ board'a kartı açar.
**Örnek:** BUG-001, FEAT-002

### ⬆️ Bottom-up (Dev keşfeder)
Ayşe/Emine implementation sırasında bir tutarsızlık görür
→ kendi açar, çoğu zaman kendi çözer (kısa yol).
**Örnek:** UI-003 (Ayşe gördü, Ayşe çözüyor)

> İki yön de **aynı şemaya** girer — pipeline kaynağı umursamaz.

---

## 👥 Roller (RACI)

| Faz | Şevval | Emine | Ayşe | Mustafa | Dilara |
|---|:--:|:--:|:--:|:--:|:--:|
| 1 · Azure Board | **R/A** | I | I | C | I |
| 2 · Senaryo | **R/A** | C | C | C | C |
| 3 · Geliştirme + Dev Summary | C | **R**(kod) | **R**(UI) | I | C |
| 4 · Hand-off | C | C | C | I | **R/A** |
| 5 · Test Deployment | C | I | I | **A** | **R** |

<small>R: yapan · A: onaylayan · C: görüşü alınan · I: bilgilendirilen</small>

---

<!-- _class: lead -->

# 🎬 3 Gerçek Vaka

Şimdi pipeline'ı **çalışırken** görelim

---

## 🐛 BUG-001 — Toplamlar Filtreyi Tanımıyor

**Discovery:** Şevval (top-down, regresyon kontrolü)
**Sayfa:** `/islemler?tab=satislar&yil=2026&portfolio=GeneralMu`

**Sorun:**
- Kullanıcı **ASTX** filtreliyor → tablo 8 satıra düşüyor ✓
- Ama KPI'lar + TOPLAM hâlâ **tüm 60 işlemi** topluyor ✗

| | Ekranda görünen (bug) | Gerçek (ASTX) |
|---|---|---|
| Net K/Z | **-$1,413.16** ❌ | **+$700.59** ✅ |
| Satış Geliri | $159,292.81 | $24,877.39 |
| Başarı | (tüm portföy) | 62.5% |

> 🔴 Kullanıcı kârdaki hisseyi **zararda** görüyor → yanlış sat/tut kararı.

---

## 🐛 BUG-001 — Pipeline Zinciri

```
Azure Work Item AB#1234  (board.yaml)
   amac: "filtre uygulanınca KPI'lar sadece görüneni toplasın"
   kabul: "ASTX → Net K/Z = +$700.59"
        │
        ▼  G1 ✅ Şevval onayı
BUG-001.scenarios.yaml   (5 senaryo, Azure'da store)
   s1 happy · s2 temizle · s3 eşleşme yok · s4 küçük harf · s5 combo
   repo_anchors: islemler.html:164-197, 296-306, 501-550
        │
        ▼  G2 ✅ Şevval review
BUG-001.solution.md (GİRDİ) ──▶ Emine kodlar ──▶ BUG-001.dev-summary.md (ÇIKTI)
   anchor + _recalcTotals()         commit AB#1234     selector + fixture
```

---

## 🐛 BUG-001 — Kök Neden & Çözüm Yönü

**Kök neden** (anchor: `islemler.html:501-550`):
`filterTable()` satırları `display:none` yapıyor ama KPI/TOPLAM
server-render `{{ totals.* }}` değerlerinde **sabit kalıyor**.

**Çözüm yönü** (Emine + AI tool):
- KPI/TOPLAM hücrelerine `data-kpi` / `data-toplam` ekle
- `filterTable()` sonuna `_recalcTotals()` → görünür satırları topla
- Server totals ilk render için kalır, client recalc üstüne biner

> 💻 **CANLI DEMO:** `.solution.md`'yi AI tool'a attach → kod üret → test yeşil.

---

## ✨ FEAT-002 — "Günlük %" Kolonu

**Discovery:** Şevval (top-down, kullanıcı geri bildirimi)
**Sayfa:** `/pozisyonlar` lot tablosu · **Assignee:** Ayşe

**İstek:**
"Günlük K/Z" ($ tutarı) var ama **yüzdesi** yok →
lot büyüklüğünden bağımsız kıyas yapılamıyor.

**Çözüm yönü:**
- "Günlük K/Z" ile "Toplam K/Z" arasına **"Günlük %"** kolonu
- Formül: `(efektif_fiyat − prev_close) / prev_close × 100`
- **AH-aware:** pre/post'ta `extended_hours_price` (sayfa mantığıyla aynı)
- Renk: yeşil/kırmızı · `prev_close` yoksa `—`

<small>6 senaryo: konum · +%· −% · prev yok · AH · kolon hizası</small>

---

## 🎨 UI-003 — "Unrealized" Başlık İşareti

**Discovery:** Ayşe (bottom-up — UI'da çalışırken kendi gördü)
**Sayfa:** `/pozisyonlar` · **Assignee:** Ayşe (keşfeden = çözen)

**Sorun:**
"Toplam K/Z" ve "K/Z %" başlıkları, bunların **gerçekleşmemiş**
(unrealized) olduğunu belirtmiyor → realized ile karışıyor.

**Çözüm yönü:**
- Başlıklara `bi-info-circle` ikonu + tooltip
- "Gerçekleşmemiş (unrealized) — pozisyon hâlâ açık..."
- **Mevcut pattern:** `fiyatlar.html`'deki `durum-info-ico` kopyalanır

> ⬆️ Bottom-up'ın gücü: keşfeden kişi en hızlı çözer, küçük scope.

---

<!-- _class: lead -->

# 👩‍💻 Developer Tarafı (Faz 3)

Work Item'ı çektikten sonra **gerçekte ne oluyor?**

---

## 👩‍💻 Developer'ın 8 Adımı

```
1. Work Item'ı çek    → Azure: New → Active
2. Branch aç          → bugfix/AB1234-totals-filter
3. Artefaktları oku   → board.yaml + scenarios + solution.md
4. AI tool ile uygula → anchor'ları besle
5. Lokal doğrula      → lint + manuel smoke
6. Commit (AB#1234)   → Work Item'a otomatik bağlanır
7. PR aç              → branch policy + reviewer
8. Dev Work Summary   → Dilara'ya hand-off ÇIKTISI
```

> `solution.md` = dev'e **GİRDİ** · `dev-summary.md` = dev'den **ÇIKTI**

---

## ⭐ Commit & İzah Disiplini

| Konu | Kötü | İyi |
|---|---|---|
| Commit | "fix bug" | "fix(islemler): totals respect filter · **AB#1234**" |
| Body | (boş) | **neden** yaptım (kod zaten ne'yi gösterir) |
| Selector | sessiz | "`[data-kpi=net-pnl]` ekledim → spec hedefler" |
| Fixture | "çalışıyor" | "GeneralMu / 2026 / 8 ASTX gerekli" |
| Sapma | gizle | "solution'dan şurada saptım çünkü ..." |

> **`AB#1234`** commit'i Azure Work Item'a otomatik bağlar → izlenebilirlik.

---

## 🛠️🤖 İki Geliştirme Yolu — Aynı Çıktı

Developer **her zaman AI kullanmaz** — yol serbest, çıktı standart:

| | 🤖 AI-Assisted | ✍️ Manuel |
|---|---|---|
| Nasıl | AI tool + anchor → `.md`'ler | Elle kod + Work Item resolution notu |
| (A) Değişiklik+selector | `ai-session.md` (diff) | resolution notu (dosya + selector) |
| (B) Dev Summary | `dev-summary.md` | Work Item yorumu (aynı başlıklar) |

> Format fark etmez — **A ve B bilgisi olmadan Dilara test'e başlamaz.**
> Çoğunlukla AI `.md`'leri tercih edilir (hız + tutarlılık).
> Örnek AI oturumu: `03-dev-solutions/BUG-001.ai-session.md`

---

## 📤 Dev Work Summary — Neden Ayrı Doküman?

Hand-off Dilara'ya geldiğinde, Dilara **kodun içine girmeden**
testi deploy edebilmeli. Bunu mümkün kılan = Dev Work Summary.

İçinde ne var:
- 🎯 **Yeni selector'lar** → Playwright spec'leri neyi hedefler
- 🗃️ **Fixture ihtiyacı** → hangi portföy/yıl/veri durumu gerekir
- ⚠️ **Sapma & risk** → solution'dan ne neden farklı
- ✅ **Lokal doğrulama** → dev neyi elle gördü

> Altın kural: **Dilara senin koduna bakmadan testi deploy edebilmeli.**

---

## 🧲 Hand-off — Dilara, Azure MCP ile Tek Çekim

Dilara işleri **ayrı ayrı toplamaz**. Azure MCP ile Work Item'ı çeker
→ ekler + PR + commit + dev notları tek seferde → **tek konsolide artifact**:

```
Azure MCP: getWorkItem(AB#1234, expand=relations,attachments,comments)
   └─▶ handoff/AB1234.bundle.md  (board + dev çıktısı + senaryo + commit)
```

**🚦 G4 Gate kuralı:** iki bilgi de var mı?
- **(A)** ne değişti + selector'lar · **(B)** Dev Summary (fixture + risk)
- Biri eksik → **bounce-back**: "test deploy edemem" yorumu + Work Item Active'e geri

> Karar artifact üzerine **yorum** olarak yazılır → iz kalır, board referans.

---

## 🚀 Faz 5 — Test Deployment (Dilara)

Gate geçildi → Dilara konsolide artifact'tan **Test Deployment** başlatır:

```
scenarios.yaml ──▶ Playwright MCP ──▶ spec üretimi/koşumu
                                          │
   repo fixtures (seed, auth, mock) ──────┤
                                          ▼
   Azure'da store edilen testler ──▶ Azure Pipeline (CI)
                                          │
                                    yeşil ▼
                              Work Item → CLOSED
```

> Test'ler **Azure'da** saklanır, **repo fixture'ları** devreye girer,
> **Playwright MCP** spec'i koşar — hepsi CI pipeline'da.

---

## 🚦 Kalite Geçitleri — Hiçbir Adım Atlanmaz

| Gate | Sorumlu | Onay kriteri |
|---|---|---|
| **G1** Board | Şevval | Amaç + kabul kriteri net, kanıt var |
| **G2** Senaryo | Şevval | happy+edge+negative, anchor dolu |
| **G3** Dev tamam | Dev (self) | kod + commit (AB#) + **Dev Summary** hazır |
| **G4** Hand-off | Dilara | selector + fixture + branch/PR eksiksiz |
| **G5** Test Deployment | Mustafa | MCP spec Azure'da yeşil → Work Item Closed |

> Bu sprintte 3 vaka da **G2'yi geçti, G3'te** bekliyor → sahnede G5'e taşıyacağız.

---

## 🔗 Traceability — "Lazer" Zinciri

```
Azure Work Item (kabul_kriteri)           ← tek girdi kaynağı
  └▶ scenarios.yaml (repo_anchors + assert)      [Azure'da store]
       └▶ solution.md (anchor + commit)          → dev GİRDİ
            └▶ commit ("... AB#1234")
                 └▶ dev-summary.md (selector + fixture)  → dev ÇIKTI
                      └▶ Playwright MCP spec → Azure Pipeline → Closed
```

- **`repo_anchors`** → AI tool'u doğru dosya:satıra lazerliyor
- **commit `AB#1234`** → Work Item ↔ kod ↔ test üçgeni Azure'da kapanıyor
- Bir story'nin izi **tek tıkla** board'dan test deployment'a sürülebilir

---

## 📊 Metrikler & Feedback Loop

Pipeline kendini ölçer ve iyileşir:

| Metrik | Ne söyler | Aksiyon |
|---|---|---|
| Senaryo değiştirilme % | Generator zayıfsa ↑ | Prompt template revize |
| "Locator yanlış" düzeltmesi | Anchor kalitesi | `data-testid` standardı |
| Eksik edge case | Normalizer açığı | Edge prompt ekle |
| Flaky test % | Mock eksiği | Mock zorunluluğu kuralı |

> Dev'in **düzeltmeleri** → examples bank → sonraki generator daha iyi.

---

## 🎯 Anahtar Mesajlar

- 🧭 **Niyet > mekanik** — board "neden", anchor "nerede", test "nasıl doğrulanır"
- 🔗 **Traceability** — Azure Work Item → senaryo → solution → commit (AB#) → test → Closed
- 🤖 **AI tool'u besleyen biziz** — structured artefakt = deterministik çıktı
- 🚦 **Gate kuralı** — (A) değişiklik+selector **ve** (B) Dev Summary olmadan Dilara başlamaz
- 🧲 **Tek referans = Azure Board** — Dilara MCP ile tek artifact çeker, bounce-back izli
- 🛠️🤖 **Yol serbest, çıktı standart** — AI ya da manuel, iki bilgi şart

---

<!-- _class: lead -->

# Q&A

**Sonraki adım:** pilot story ataması
→ BUG-001'i bu akışla baştan sona koşalım

Teşekkürler 🙏
