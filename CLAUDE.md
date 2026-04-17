# Frigya — CLAUDE.md
**US Hisse Senedi Vergi Takip Sistemi (Türk mevzuatı, FIFO)**

Bu dosya Claude Code'un projeyi sıfırdan anlayarak devam edebilmesi için hazırlanmıştır.

---

## 1. PROJE ÖZETI

ABD borsasındaki alım-satım işlemlerinin Türk vergi mevzuatına uygun şekilde takip edilmesi. İşlemler aracı kurum üzerinden gerçekleştiriliyor. Hesaplama yöntemi **FIFO (First In First Out)** — aracı kurum'ın da kullandığı resmi yöntem.

### Çıktı Dosyası
```
/Tax_Portfolilo/Kar_Zarar_Analizi_2025_2026.xlsx
```
4 sayfa:
| Sıra | Sayfa Adı | İçerik | Para Birimi |
|------|-----------|---------|-------------|
| 1 | **Tarihe Göre 2026** | 51 satış işlemi, FIFO, CSV kaynaklı | USD |
| 2 | **Sembole Göre 2026** | Sembole göre gruplu özet | USD |
| 3 | **Tarihe Göre 2025** | 101 satış işlemi, FIFO, aylık PDF kaynaklı | USD |
| 4 | **Sembole Göre 2025** | Sembole göre gruplu özet | USD |

---

## 2. KLASÖR YAPISI

```
/Tax_Portfolilo/
├── CLAUDE.md                          ← bu dosya
├── Kar_Zarar_Analizi_2025_2026.xlsx   ← ANA ÇIKTI
├── 2025/
│   ├── Haziran 2025.pdf
│   ├── Temmuz 2025.pdf
│   ├── Ağustos 2025.pdf
│   ├── Eylül 2025.pdf
│   ├── Ekim 2025.pdf
│   ├── Kasım 2025.pdf
│   └── Aralık 2025.pdf
└── 2026/
    ├── 2026_Kar_Zarar_Analizi.xlsx    ← eski dosya (yerini aldı)
    └── Mart 2026.pdf
```

Ayrıca uploads klasöründe:
```
2025 Vergi Durumu Özeti.pdf   ← TRY bazlı resmi aracı kurum FIFO özeti (referans)
midas-emir-gecmisi-tumu-*.csv ← 2026 işlem geçmişi CSV (tumu = tüm emirler)
Şubat 2026.pdf                ← Şubat 2026 ekstresi
```

---

## 3. VERİ KAYNAKLARI

### 2026 Verileri → CSV
- Kaynak: `midas-emir-gecmisi-tumu-YYYY-MM-DDTHH_MM_SS.csv` (Midas CSV formatı)
- **"tumu" CSV'si** iptal edilmiş emirleri de içerir → `Gerçekleşen Miktar > 0` filtresi zorunlu
- CSV sütunları: Tarih, İşlem Tipi, Sembol, Gerçekleşen Miktar, Ortalama İşlem Fiyatı, İşlem Tutarı, ...
- CSV 3 Nisan 2026'ya kadar işlemleri içeriyor

### 2025 Verileri → Aylık PDF Ekstreler
- Kaynak: Haziran–Aralık 2025 aylık hesap ekstreleri
- Her PDF → "Yatırım İşlemleri" tablosu → Alış/Satış/İptal sütunları
- **İptal Edildi** satırları atlanır, sadece **Gerçekleşti** AND **Gerçekleşen Adet > 0** işlenir
- Haziran 2025 öncesi ay PDF'leri yok (hesap 20/02/2025'te açılmış)

### 2025 Vergi Durumu Özeti (referans)
- TRY bazlı, TCMB alış kuru kullanılarak hesaplanmış
- ÜFE endekslemesi uygulanmış (alış-satış arası enflasyon > %10 ise)
- 94 satış işlemi, Toplam Kazanç: ₺386.119,29 / Beyana Tabi: ₺372.985,22
- **Eşik aşıldı → Beyan gerekli** (₺18.000 limiti)
- Bu dosya USD hesabı için kaynak değil, sadece TRY referans

---

## 4. EXCEL SAYFA YAPISI (4 sayfa birebir aynı sütunlar)

### Tarihe Göre (hem 2025 hem 2026)
| Kolon | Başlık |
|-------|--------|
| A | Tarih |
| B | Sembol |
| C | Satış Adedi |
| D | Satış Fiyatı (USD) |
| E | Satış Geliri (USD) |
| F | Alış Maliyeti (USD) |
| G | Kâr / Zarar (USD) |
| H | Durum (KÂR/ZARAR) |
| I | Kâr/Zarar Yüzdesi % |

### Sembole Göre (hem 2025 hem 2026)
| Kolon | Başlık |
|-------|--------|
| A | Sembol |
| B | Son Satış Tarihi |
| C | Son Satış Fiyatı (USD) |
| D | Toplam İşlem |
| E | Başarılı İşlem |
| F | Başarısız İşlem |
| G | Başarı Oranı % |
| H | Toplam Adet |
| I | Satış Geliri (USD) |
| J | Alış Maliyeti (USD) |
| K | Net Kâr/Zarar (USD) |
| L | Kâr/Zarar Yüzdesi % |
| M | Toplam KÂR (USD) |
| N | Toplam ZARAR (USD) |

### Renk Kodları
```python
KAR_FILL   = "E0F0E0"  # açık yeşil — kâr satırları
ZARAR_FILL = "FFE0E0"  # açık kırmızı — zarar satırları
TOT_FILL   = "D6E4F0"  # açık mavi — toplam satırı
HDR_FILL   = "1F4E79"  # koyu mavi — başlık
EKS_FILL   = "FFF3CD"  # amber — eksik lot uyarısı
ALT_FILL   = "F5F9FF"  # çok açık mavi — alternatif satır
```

---

## 5. FIFO MOTORU

### Temel Kural
Her sembol için ayrı bir kuyruk (list). Alışlarda kuyruğa eklenir, satışlarda önden tüketilir.

### Python FIFO Kodu
```python
from collections import defaultdict

fifo = defaultdict(list)  # symbol → [[qty, price, cost], ...]

for tarih_s, sembol, islem, adet, fiyat, toplam in transactions:
    if islem == "Alış":
        fifo[sembol].append([adet, fiyat, toplam])
    else:  # Satış
        kalan      = adet
        total_cost = 0.0
        eksik_lot  = False

        while kalan > 1e-7:
            if not fifo[sembol]:
                eksik_lot = True
                break
            lot_qty, lot_price, lot_cost = fifo[sembol][0]
            if lot_qty <= kalan + 1e-7:
                consumed    = min(lot_qty, kalan)
                frac        = consumed / lot_qty if lot_qty > 1e-10 else 0
                total_cost += lot_cost * frac
                kalan      -= consumed
                fifo[sembol].pop(0)
            else:
                oran        = kalan / lot_qty
                partial     = lot_cost * oran
                total_cost += partial
                fifo[sembol][0] = [lot_qty - kalan, lot_price, lot_cost - partial]
                kalan = 0

        kar_zarar = satis_geliri - total_cost
```

### Maliyet Hesabı
- Alış maliyeti = `İşlem Tutarı` (adet × ortalama fiyat)
- Satış geliri = `İşlem Tutarı` (adet × ortalama fiyat)
- Komisyon ($1.50/işlem) CSV/PDF'de ayrı gösterilir, fiyata dahil değil
- Basitlik için komisyon maliyet bazına eklenmemiştir (fark küçük)

---

## 6. KRİTİK DÜZELTMELER VE KARARLAR

### 6.1 ROBN — Yıl Sonu Devir Lot Sorunu (2026)
**Problem:** CSV sadece Aralık 2025'te alınan 15 ROBN lotunu içeriyordu (15 shares @ $68.72/share, $1,029.78). Oysa 2026'ya devreden 37 shares vardı.

**Çözüm:** Kullanıcının 2025 ROBN işlem tablosu alındı, manuel FIFO hesaplandı:
```python
# 2026 başına devreden ROBN lot kuyruğu (4 ayrı lot):
# 10/25/2025: 10 shares @ $99.28  → maliyet $992.80
# 11/05/2025:  5 shares @ $97.20  → maliyet $486.00
# 11/05/2025:  5 shares @ $101.15 → maliyet $505.75
# 12/22/2025: 12 shares @ $70.21  → maliyet $842.52
# 12/22/2025: 15 shares @ $67.65  → maliyet $1,014.78  (yalnızca 37 shares toplam)
# Toplam maliyet: $2,897.34 (37 shares)
```

**Sonuç:** ROBN 15/01/2026 satışı:
- Satış Geliri: $2,248.12 (37 shares @ $59.76)
- Alış Maliyeti: $2,897.34
- **K/Z: -$649.22 (ZARAR)** — önceki yanlış hesap +$1,218.34 KÂR'dı

### 6.2 TRON — Eksik Lot (2025)
**Problem:** TRON 01/07/2025 satışı (15 shares @ $6.71 = $100.65). Mayıs 2025 veya öncesinde alınmış, PDF verisi yok.
**Durum:** `eksik_lot=True`, maliyet=$0, Excel'de amber renkle işaretli (KÂR\*)

### 6.3 TQQQ — Kısmi Eksik Lot (2025)
**Problem:** 13/12/2025 TQQQ satışı (16.6 shares). Önceki lotlar tükenmiş, bu satış için yeterli lot yok.
**Durum:** `eksik_lot=True`, Excel'de amber (ZAR\*)

### 6.4 "tumu" vs "gerceklesti" CSV Farkı
- `tumu` = tüm emirler (iptal dahil)
- `gerceklesti` = sadece gerçekleşenler
- **tumu CSV kullanılırken `Gerçekleşen Miktar > 0` filtresi şart**

### 6.5 Mart 2026 PDF Mükerrer Kontrolü
Mart 2026 satışları (RKLX 03/03, IREX 10/03, NVDL 16/03) zaten CSV'de var → ekleme yapılmadı.

---

## 7. 2026 VERİLERİ (51 İşlem)

### Özet
- Dönem: 02/01/2026 – 03/04/2026
- Toplam Satış Geliri: (Excel'den güncel)
- ROBN düzeltmesi dahil

### CSV'den 2026 FIFO Nasıl Hesaplanır
```python
import pandas as pd
from collections import defaultdict

df = pd.read_csv("midas-emir-gecmisi-tumu-*.csv", encoding="utf-8-sig")
# Filtrele: sadece gerçekleşen işlemler
df = df[df["Gerçekleşen Miktar"] > 0].copy()
# Tarih sırala
df["Tarih"] = pd.to_datetime(df["Tarih"], dayfirst=True)
df = df.sort_values("Tarih")

fifo = defaultdict(list)
# ROBN için 2025 devir lotları baştan ekle:
robn_carry = [
    [10.0, 99.28,  992.80],
    [ 5.0, 97.20,  486.00],
    [ 5.0, 101.15, 505.75],
    [12.0, 70.21,  842.52],
    [15.0, 67.65, 1014.78],
]
for lot in robn_carry:
    fifo["ROBN"].append(lot)

# Sonra CSV satırlarını işle...
```

---

## 8. 2025 VERİLERİ (101 İşlem)

### Özet
- Dönem: 18/06/2025 – 31/12/2025
- Toplam Satış Geliri: $122,024.09
- Toplam Alış Maliyeti: $113,264.66
- Net K/Z: **+$8,759.43**
- Başarı Oranı: %77.2 (78 KÂR / 23 ZARAR)
- Eksik Lot: 2 işlem (TRON, TQQQ)

### En İyi Performans (Sembole Göre 2025)
| Sembol | Net K/Z (USD) |
|--------|--------------|
| ASTX | +$1,794.75 |
| SOXL | +$1,605.45 |
| AMDL | +$1,554.13 |
| RKLX | +$1,306.84 |
| AGQ | +$941.14 |

---

## 9. PYTHON SCRIPT'LERİ

### Script 1: `build_4sheet.py` — İlk kurulum (2025 TRY + 2026 rename)
Artık kullanılmıyor, yerini `build_2025_usd.py` aldı. Ama 2026 sheet rename için logic:
```python
# Eski adından yeni ada:
# "Tarihe Göre"  → "Tarihe Göre 2026"
# "Sembole Göre" → "Sembole Göre 2026"
for ws in wb.worksheets:
    if ws.title == "Tarihe Göre":
        ws.title = "Tarihe Göre 2026"
    elif ws.title == "Sembole Göre":
        ws.title = "Sembole Göre 2026"
```

### Script 2: `build_2025_usd.py` — Ana script (2025 USD FIFO)

**Çalıştırma:**
```bash
python3 build_2025_usd.py
```

**Yaptığı işlemler:**
1. `Kar_Zarar_Analizi_2025_2026.xlsx` dosyasını açar
2. Eski TRY bazlı 2025 sayfalarını siler
3. 2025 USD FIFO hesabını çalıştırır (101 satış, 45 sembol)
4. "Tarihe Göre 2025" ve "Sembole Göre 2025" sayfalarını ekler
5. Sheet sırası: 2026 → 2025
6. Aynı dosyaya kaydeder

**İşlem verisi (TX listesi) scriptin içinde hardcoded** — 230+ satır tuple listesi.

---

## 10. YENİ AY NASIL EKLENİR

Yeni bir aylık PDF (örn. Ocak 2026) geldiğinde:

### Adım 1: PDF'den işlemleri çıkar
```
Agent'a sor: "Bu PDF'den tüm Yatırım İşlemleri'ni çıkar,
sadece Gerçekleşti + Gerçekleşen Adet > 0 olanları,
format: (YYYY-MM-DD, SEMBOL, Alış/Satış, adet, fiyat, toplam)"
```

### Adım 2: Mükerrer kontrolü
CSV'de zaten var mı kontrol et. 2026 CSV 3 Nisan 2026'ya kadar kapsıyor.
```python
# Yeni PDF işlemini CSV satırlarıyla karşılaştır:
# Aynı tarih + sembol + adet + yön → mükerrer, atla
```

### Adım 3: TX listesine ekle
`build_2025_usd.py` veya yeni bir `build_2026_update.py` içindeki TX listesine tuple ekle.

### Adım 4: Scripti çalıştır
```bash
python3 build_2026_update.py
```

---

## 11. ROADMAP

### Yakın Hedef: Grafik / Dashboard
- Aylık K/Z trendi (bar chart)
- Sembol bazlı performans (horizontal bar)
- Kümülatif K/Z eğrisi
- Önerilen format: Excel'e ek bir "Dashboard" sayfası veya ayrı HTML dosyası

### Yakın Hedef: Otomatik Güncelleme
Yeni PDF veya CSV yüklenince FIFO'yu otomatik yeniden hesapla.
```python
# Yaklaşım A: Schedule task (Cowork)
# Yaklaşım B: Python watch script — yeni dosya tespit edince çalışır
# Yaklaşım C: Claude Code hook — /update komutu ile tetiklenir
```

### Gelecek: Hisse/ETF Bazında İşlem Geçmişi Sayfası
Her sembol için ayrı sayfa: tüm alış-satış tarihçesi, pozisyon değişimi, ortalama maliyet.
**Bu özelliği Claude Code tarafında geliştirmek istiyorsun.**

Örnek veri yapısı:
```python
# SOXL sayfası için:
# Tarih | İşlem | Adet | Fiyat | Tutar | Kümülatif Pozisyon | Ort. Maliyet
# 21/07 | Alış  | 21.4 | 28.06 | 600   | 21.4               | 28.06
# 22/09 | Alış  | 28.9 | 34.58 | 1000  | 50.3               | 31.80
# 30/09 | Satış | 25.2 | 33.95 | 854   | 25.1               | 34.58 (FIFO)
# ...
```

---

## 12. TEKNİK NOTLAR

### openpyxl Kullanımı
```bash
pip install openpyxl --break-system-packages
```

Temel pattern:
```python
from openpyxl import load_workbook
wb = load_workbook("dosya.xlsx")
ws = wb["Sayfa Adı"]
# wb.create_sheet("Yeni Sayfa")
# del wb["Eski Sayfa"]
wb.save("dosya.xlsx")
```

Sheet sıralaması:
```python
name_map = {ws.title: ws for ws in wb.worksheets}
wb._sheets = [name_map[n] for n in ["Sayfa1","Sayfa2","Sayfa3"]]
```

### CSV Encoding
```python
df = pd.read_csv("midas.csv", encoding="utf-8-sig", sep=",")
# veya sep=";" olabilir, kontrol et
```

### PDF'den İşlem Çıkarma
- En güvenilir yöntem: Agent'a PDF okutmak
- PyMuPDF veya pdfplumber ile programatik okuma da çalışır ama tablo hizalaması bozulabilir

### Tarih Formatları
- CSV: `DD/MM/YYYY HH:MM:SS` formatında
- PDF: `DD/MM/YY HH:MM:SS` formatında
- Excel hücre formatı: `DD/MM/YYYY`

---

## 13. BAĞLAM: VERGİ HESABI (Türk Mevzuatı)

| Konu | Detay |
|------|-------|
| Hesaplama yöntemi | FIFO |
| Döviz kuru | TCMB dolar alış kuru — işlem gününden ÖNCEKİ günün kuru |
| ÜFE endekslemesi | Alış-satış arası enflasyon > %10 ise alış maliyetine yansıtılır |
| Beyan eşiği | ₺18.000 (beyana tabi kazanç toplamı) |
| 2025 durumu | Eşik AŞILDI → Beyan gerekli |
| Stopaj | IRS'e ödenen temettü vergisi — aracı kurum tarafından kesiliyor |

**Önemli:** Bu Excel USD bazlıdır. Resmi Türk vergi beyanı için TRY dönüşümü gerekir (Vergi Durumu Özeti = resmi TRY hesabı).

---

## 14. HIZLI BAŞLANGIÇ (Claude Code için)

Projeye yeni başlayan Claude Code bu adımları takip etmeli:

```bash
# 1. Mevcut dosyaları gör
ls /Tax_Portfolilo/

# 2. Ana Excel dosyasını kontrol et
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('Tax_Portfolilo/Kar_Zarar_Analizi_2025_2026.xlsx')
for ws in wb.worksheets:
    print(ws.title, '—', ws.max_row, 'satır')
"

# 3. Yeni işlem eklemek için
# → TX listesine tuple ekle
# → build_2025_usd.py'yi çalıştır (2025 için)
# → veya 2026 CSV scriptini güncelle (2026 için)
```

---

*Son güncelleme: Nisan 2026 | Cowork oturumundan üretilmiştir*
