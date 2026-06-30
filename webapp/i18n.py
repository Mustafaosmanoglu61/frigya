"""
Basit kaynak-metin tabanlı i18n.

Kullanım (template): {{ t('İşlemler') }}
- lang == 'tr'  → metin olduğu gibi döner
- lang == 'en'  → TRANSLATIONS sözlüğünden İngilizce karşılığı, yoksa orijinal

Yeni metin çevirmek için: TRANSLATIONS sözlüğüne Türkçe→İngilizce satırı ekle.
"""

SUPPORTED_LANGS = ("tr", "en")
DEFAULT_LANG = "tr"


def normalize_lang(lang) -> str:
    lang = (lang or "").strip().lower()
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


# Türkçe kaynak metin → İngilizce
TRANSLATIONS = {
    # ─── Navbar / ortak ───────────────────────────────────────────────
    "Dashboard": "Dashboard",
    "İşlemler": "Transactions",
    "Semboller": "Symbols",
    "Açık Pozisyonlar": "Open Positions",
    "Fiyatlar": "Prices",
    "Yönetim": "Admin",
    "Çıkış": "Logout",
    "Portföy:": "Portfolio:",
    "★ Süper Portföy (Tümü)": "★ Super Portfolio (All)",
    "Dil": "Language",
    "Türkçe": "Turkish",
    "İngilizce": "English",

    # ─── Süper portföy şeridi ─────────────────────────────────────────
    "Süper Portföy": "Super Portfolio",
    "tüm portföylerin toplamı gösteriliyor": "showing the sum of all portfolios",
    "salt-okunur": "read-only",
    "İşlem eklemek/düzenlemek için yukarıdan gerçek bir portföy seçin.":
        "Select a real portfolio above to add/edit transactions.",
    "Süper Portföy — birleşik izleme listesi (salt-okunur)":
        "Super Portfolio — combined watchlist (read-only)",
    "Süper Portföy — tüm portföylerin toplamı (salt-okunur)":
        "Super Portfolio — sum of all portfolios (read-only)",

    # ─── Genel butonlar / durumlar ────────────────────────────────────
    "İşlem Ekle": "Add Transaction",
    "Ekle": "Add",
    "Sil": "Delete",
    "Düzenle": "Edit",
    "Kaydet": "Save",
    "İptal": "Cancel",
    "Kapat": "Close",
    "Hedefleri Kaydet": "Save Targets",
    "Hedef Ayarla": "Set Target",
    "Tümü": "All",
    "Veri yok": "No data",
    "KÂR": "PROFIT",
    "ZARAR": "LOSS",
    "Kâr": "Profit",
    "Zarar": "Loss",
    "Tarih": "Date",
    "Sembol": "Symbol",
    "Adet": "Qty",
    "Fiyat": "Price",
    "Fiyat (USD)": "Price (USD)",
    "Tutar": "Amount",
    "Yön": "Side",
    "Alış": "Buy",
    "Satış": "Sell",
    "Durum": "Status",
    "İşlem": "Trade",
    "Toplam": "Total",
    "Yükleniyor...": "Loading...",
    "Yükleniyor…": "Loading…",

    # ─── Dashboard ────────────────────────────────────────────────────
    "Dönem:": "Period:",
    "Temizle": "Clear",
    "Hoş geldiniz": "Welcome",
    "Başlamak için ilk portföyünüzü oluşturun.": "Create your first portfolio to get started.",
    "Portföy adı": "Portfolio name",
    "Açıklama (isteğe bağlı)": "Description (optional)",
    "Oluştur": "Create",
    "Satış:": "Sales:",
    "İşlem:": "Trades:",
    "Başarı:": "Success:",
    "KÂR:": "PROFIT:",
    "ZARAR:": "LOSS:",
    "Açık Pozisyon:": "Open Positions:",
    "Başarı Oranı:": "Success Rate:",
    "Toplam Zarar:": "Total Loss:",
    "NET K/Z": "NET P&L",
    "TOPLAM NET K/Z": "TOTAL NET P&L",
    "Açık Pozisyon": "Open Position",
    "sembol": "symbols",
    "Başarı Oranı": "Success Rate",
    "Toplam Zarar": "Total Loss",
    "Satış": "Sales",
    "Başarı": "Success",
    "Haftalık Kâr / Zarar": "Weekly Profit / Loss",
    "Aylık Kâr / Zarar": "Monthly Profit / Loss",
    "Aylık": "Monthly",
    "Haftalık": "Weekly",
    "Kümülatif K/Z Eğrisi — Haftalık": "Cumulative P&L Curve — Weekly",
    "Kümülatif K/Z Eğrisi — Aylık": "Cumulative P&L Curve — Monthly",
    "Sembol Performansı (Top 15)": "Symbol Performance (Top 15)",
    "Sembol — Realized": "Symbol — Realized",
    "Sembol — Unrealized": "Symbol — Unrealized",
    "Realized": "Realized",
    "Unrealized": "Unrealized",
    "Maliyet": "Cost",
    "Mevcut Değer": "Market Value",
    "Maliyet Dağılımı": "Cost Distribution",
    "Sektör — Maliyet": "Sector — Cost",
    "Sektör — Mevcut Değer": "Sector — Market Value",
    "GERÇEKLEŞMEMİŞ K/Z": "UNREALIZED P&L",
    "Açık:": "Open:",
    "Sektör / Klasman Dağılımı": "Sector / Class Distribution",
    "Sektör Özet Tablosu": "Sector Summary Table",
    "Tag": "Tag",
    "Maliyet %": "Cost %",
    "Mevcut Değer %": "Market Value %",
    "K/Z %": "P&L %",
    "Realized K/Z": "Realized P&L",
    "Unrealized K/Z": "Unrealized P&L",

    # ─── Semboller sayfası ────────────────────────────────────────────
    "Sembole Göre Özet": "Summary by Symbol",
    "Son Satış": "Last Sale",
    "Son Fiyat": "Last Price",
    "Başarı %": "Success %",
    "Toplam Adet": "Total Qty",
    "Satış Geliri": "Sale Proceeds",
    "Alış Maliyeti": "Cost Basis",
    "Net K/Z": "Net P&L",
    "Toplam KÂR": "Total PROFIT",
    "Toplam ZARAR": "Total LOSS",
    "Sektör / Klasman": "Sector / Class",

    # ─── Pozisyonlar sayfası ──────────────────────────────────────────
    "Açık Pozisyonlar": "Open Positions",
    "Lot": "Lot",
    "Ort. Maliyet": "Avg. Cost",
    "Ort Maliyet": "Avg Cost",
    "Maliyet Bazı": "Cost Basis",
    "Alış Tarihi": "Buy Date",
    "Alış Fiyatı": "Buy Price",
    "Gün": "Days",
    "Günlük K/Z": "Daily P&L",
    "Toplam K/Z": "Total P&L",
    "İşlem #": "Trade #",
    "Anlık Fiyat": "Live Price",
    "Devir": "Carry",
    "Normal": "Normal",
    "Piyasa Değeri": "Market Value",
    "Mevcut": "Current",
    "Unrealized K/Z %": "Unrealized P&L %",
    "Toplam Maliyet:": "Total Cost:",
    "Gerçekleşmemiş K/Z:": "Unrealized P&L:",

    # ─── İşlemler sayfası ─────────────────────────────────────────────
    "Tüm İşlemler": "All Transactions",
    "Satışlar": "Sales",
    "Satış İşlemleri": "Sell Transactions",
    "Manuel İşlem Ekleme": "Add Manual Transaction",
    "İşlem Tipi": "Transaction Type",
    "Satış Adedi": "Sell Qty",
    "Satış Fiyatı": "Sell Price",
    "Kâr / Zarar": "Profit / Loss",
    "Portföy": "Portfolio",

    # ─── Fiyatlar / izleme listesi ────────────────────────────────────
    "Fiyatlar & İzleme Listesi": "Prices & Watchlist",
    "İzleme Listesi": "Watchlist",
    "Pozisyonlar": "Positions",
    "Son:": "Last:",
    "Hiç güncellenmedi": "Never updated",
    "Güncelle": "Update",
    "Otomatik": "Auto",
    "İzleme listesi boş. Yukarıdan sembol ekleyebilirsiniz.":
        "Watchlist is empty. You can add symbols above.",
    "Hedef": "Target",
    "Hedef Kar": "Target Profit",
    "Hedef Fiyat": "Target Price",
    "Hedef Fiyat (USD)": "Target Price (USD)",
    "Taban Fiyat": "Floor Price",
    "Taban Fiyat ($)": "Floor Price ($)",
    "Hedef Kazanç ($)": "Target Gain ($)",
    "Hedefe %": "To Target %",
    "Güncel fiyat yükleniyor...": "Loading current price...",
    "Not": "Note",
    "Resim Ekle": "Add Image",
    "Sembol gir (örn: AAPL)": "Enter symbol (e.g. AAPL)",

    # ─── Sembol detay ─────────────────────────────────────────────────
    "FIFO Eşleşme": "FIFO Match",
    "Açık Pozisyon": "Open Position",
    "İşlem Düzenle": "Edit Transaction",
    "Gerçekleşen K/Z": "Realized P&L",
    "Açık Pozisyon (Unrealized)": "Open Position (Unrealized)",
    "Özet": "Summary",
    "Portföy hedefleri (salt-okunur):": "Portfolio targets (read-only):",
    "Bu sembol için hiçbir portföyde hedef tanımlı değil.":
        "No target defined in any portfolio for this symbol.",
    "Tag tüm portfolyolarda ortaktır — sektör bazlı dashboard grafiğinde kullanılır.":
        "Tag is shared across all portfolios — used in sector-based dashboard charts.",
}


TRANSLATIONS.update({
    # ─── Dashboard sektör tablosu başlıkları ──────────────────────────
    "Maliyet %": "Cost %",
    "Mevcut Değer %": "Market Value %",

    # ─── Fiyatlar — izleme listesi kolonları ──────────────────────────
    "Fiyat / Değişim": "Price / Change",
    "After Market": "After Market",
    "Taban": "Floor",
    "Tabana %": "To Floor %",
    "Son Alış": "Last Buy",
    "Satış Sonrası %": "After-Sale %",
    "Alıştan Gün": "Days Since Buy",
    "Satıştan Gün": "Days Since Sale",
    "S.Satış Lot": "L.Sell Lot",
    "S.Alış Tutar": "L.Buy Amt",
    "S.Satış Tutar": "L.Sell Amt",
    "S.Alış Lot": "L.Buy Lot",
    "Son K/Z %": "Last P&L %",
    "Eşik": "Threshold",
    "Etiket": "Label",
    "Bölge": "Zone",

    # ─── Sembol detay — tablo kolonları ───────────────────────────────
    "Kaynak Yılı": "Source Year",
    "K/Z": "P&L",
    "Tüketilen Adet": "Consumed Qty",
    "Tüketilen Maliyet": "Consumed Cost",
    "Tür": "Type",
    "Lot #": "Lot #",
    "Ortalama Maliyet": "Average Cost",
    "Buy Price": "Buy Price",

    # ─── Modallar / filtreler / durum rehberi ─────────────────────────
    "Yön: Tümü": "Side: All",
    "Sıfırla": "Reset",
    "Tümünü Göster": "Show All",
    "Çıkış Hesapla": "Exit Calculator",
    "— Çıkış Hesapla": "— Exit Calculator",
    "Çıkış Fiyatı ($)": "Exit Price ($)",
    "↑ Yükselişte": "↑ Rising",
    "↓ Düşüşte": "↓ Falling",
    "→ Yatay": "→ Flat",

    # ─── Boş durum / kart başlığı / özet etiketleri ───────────────────
    "Veri yok": "No data",
    "Açık pozisyon bulunmuyor.": "No open positions.",
    "işlem": "trades",
    "Gerçekleşmemiş K/Z": "Unrealized P&L",
    "Ger. K/Z:": "Real. P&L:",
    "g açık": "d open",
    "Filtre:": "Filter:",
    "Açık İşlem Detayı": "Open Lot Details",
    "Kazanan": "Winning",
    "Başarı": "Success",
    "Tüm Yıllar": "All Years",
    "Gelir:": "Income:",
    "Maliyet:": "Cost:",
    "Net:": "Net:",
    "Ortalama Maliyet:": "Average Cost:",
    "TOPLAM": "TOTAL",
})


def translate(text, lang: str = DEFAULT_LANG) -> str:
    """lang 'en' ise sözlükten çevir; yoksa/tr ise orijinali döndür."""
    if lang == "en":
        return TRANSLATIONS.get(text, text)
    return text
