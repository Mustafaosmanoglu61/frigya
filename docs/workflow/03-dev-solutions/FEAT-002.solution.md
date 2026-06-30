# ✨ FEAT-002 — "Günlük %" Kolonu

> **Story:** Lot tablosuna günlük hareket yüzdesi kolonu
> **Assignee:** Ayşe (UI) · **Reviewer:** Şevval (test) → Mustafa (merge)
> **Test spec:** `tests/feat-002-daily-pct-column.spec.ts`
> **Senaryolar:** `docs/workflow/02-test-scenarios/FEAT-002.scenarios.yaml`
> **Azure Work Item:** `AB#1235` ← commit'ler `AB#1235` ile bağlanır

---

## 🎯 Ne yapacağız (1 cümle)
`/pozisyonlar` lot tablosunda "Günlük K/Z" ile "Toplam K/Z" arasına, günlük hareketin yüzdesini gösteren **"Günlük %"** kolonu ekle.

## 📍 Anchor — Dokunulacak Yerler

| Dosya | Satır | Ne yapılacak |
|---|---|---|
| `webapp/templates/pozisyonlar.html` | 132-133 | thead'e `<th>Günlük %</th>` ekle (Günlük K/Z ↔ Toplam K/Z arası) |
| `webapp/templates/pozisyonlar.html` | tbody (`<tr>` döngüsü) | her satıra `<td class="lot-daily-pct">—</td>` ekle (aynı konum) |
| `webapp/templates/pozisyonlar.html` | 491-499 | widget günlük formülü = **referans** (kopyalama, paralel yaz) |
| `webapp/templates/pozisyonlar.html` | 577-582 | `lot-pnl-pct` hesabının yanına `lot-daily-pct` hesabı ekle |
| `webapp/templates/pozisyonlar.html` | tfoot | yeni kolon için boş `<td></td>` ekle (hizalama) |

## 🛠️ Yaklaşım (yön)

- Kolon başlığı `col-draggable` class'lı olsun (diğerleriyle tutarlı, sürüklenebilir).
- Hesap, fiyat güncelleme fonksiyonunun içinde `lot-pnl-pct` ile **aynı yerde** yapılsın.
- Formül: `(efektif_fiyat - prev_close) / prev_close * 100`
  - `efektif_fiyat`: AH aktifse `extended_hours_price`, değilse `current_price`
    (sayfadaki diğer kolonların AH mantığıyla **birebir aynı** — yeni mantık icat etme).
- Renk: `text-success` / `text-danger` (mevcut `lot-pnl-pct` ile aynı pattern).
- `prev_close` yok/null → `'—'`, renk class'ı ekleme.

**Pseudo:**
```
# fiyat güncelleme döngüsünde, her lot satırı için:
eff   = AH_aktif ? ext_price : current_price
if prev_close yoksa:  dailyPctCell = '—'
else:
   dpct = (eff - prev_close) / prev_close * 100
   dailyPctCell = fmtPct(dpct)   # +N.N% / -N.N%
   renk = dpct >= 0 ? success : danger
```

## ⚠️ Dikkat Et
- **Kolon sayısı tutarlılığı:** thead + tbody + tfoot üçünde de yeni `<td>/<th>` olmalı, yoksa hizalama kayar (test `FEAT-002.s6` bunu yakalar).
- AH efektif fiyat için **mevcut helper'ı kullan** — `_effPrice()` benzeri mantık sayfada zaten var; yeniden yazma.
- `fmtPct` / renk helper'ları zaten tanımlı → tekrar tanımlama.
- "Günlük K/Z" ($ tutarı) zaten var; bu kolon onun **yüzdesi**, formülü tutarlı tut.

## ✅ Bittiği Nasıl Anlaşılır (acceptance)
- [ ] `FEAT-002.s1`: "Günlük %" başlığı doğru konumda (Günlük K/Z ↔ Toplam K/Z)
- [ ] `FEAT-002.s2`: +10% senaryosu yeşil
- [ ] `FEAT-002.s3`: -10% senaryosu kırmızı
- [ ] `FEAT-002.s4`: prev_close yok → `—`
- [ ] `FEAT-002.s5`: AH aktifken AH fiyatından hesap
- [ ] `FEAT-002.s6`: thead↔tbody kolon sayısı eşit
- [ ] Manuel: dark mode + kolon sürükle-bırak bozulmuyor

## 📝 Commit Mesajı Şablonu
```
feat(pozisyonlar): add "Günlük %" column to open-positions lot table [FEAT-002]

New column between "Günlük K/Z" and "Toplam K/Z" showing daily move
as a percentage. AH-aware: uses extended_hours_price during PRE/POST,
falls back to current_price. Green/red colored, '—' when prev_close
is unavailable.

Fixes AB#1235
Tests: tests/feat-002-daily-pct-column.spec.ts
```
> `Fixes AB#1235` → PR tamamlanınca Azure Work Item otomatik kapanır.

## 📎 Work Item'a Attach Edilecekler
1. **Dev Work Summary** (`FEAT-002.dev-summary.md` — selector + fixture)
2. Commit hash (`AB#1235` linkli)
3. `npx playwright test feat-002` yeşil log
4. Screenshot: yeni kolonlu tablo (light + dark)
