# 📤 Dev Work Summary — ŞABLON

> **Bu dosya geliştirmenin ÇIKTISIDIR** (solution.md = girdi, bu = çıktı).
> Developer doldurur, Work Item'a attach eder. Faz 4 hand-off'ta Dilara'nın
> **test deployment** için ihtiyaç duyduğu her şeyi içerir.
>
> Altın kural: **Dilara senin koduna girmeden testi deploy edebilmeli.**

---

## 🔖 Kimlik
| Alan | Değer |
|---|---|
| Work Item | `AB#____` |
| Story | `<BUG/FEAT/UI>-___` |
| Developer | `<isim>` |
| Branch | `<bugfix/AB____-...>` |
| PR | `<PR-link>` |
| Commit(ler) | `<hash> (squash sonrası)` |
| Durum | `Resolved` (test deployment bekliyor) |

## 🔧 Ne Değişti (test yüzeyi)
> Dilara'nın hangi dosyaları/davranışı test etmesi gerektiğini bilmesi için.

| Dosya | Değişim türü | Test'i ilgilendiren not |
|---|---|---|
| `<dosya:satır>` | `<ekleme/değişiklik>` | `<ne test edilmeli>` |

## 🎯 Yeni / Değişen Selector'lar ⭐
> Playwright spec'lerin hedefleyeceği locator'lar. **Eksiksiz listele.**

| Selector | Nerede | Ne gösterir |
|---|---|---|
| `[data-...]` | `<sayfa/komponent>` | `<anlamı>` |

## 🗃️ Fixture / Veri İhtiyacı ⭐
> Testin koşması için gereken DB durumu / seed / mock. Dilara bunu deploy eder.

- **Portföy:** `<örn. GeneralMu>`
- **Yıl/dönem:** `<örn. 2026>`
- **Gereken kayıtlar:** `<örn. 60 satış, 8'i ASTX>`
- **Mock gerekli mi:** `<evet/hayır — hangi endpoint>`
- **Auth:** `<storageState / admin>`

## 🧪 Lokal Doğrulama (yaptıklarım)
- [ ] Manuel smoke: `<kabul kriteri elle doğrulandı mı>`
- [ ] Console temiz
- [ ] Lint clean
- [ ] `scenarios.yaml` beklenen değerleri elle teyit

## ⚠️ Sapmalar & Riskler
> solution.md'den saptıysan **neden**. Tam kapatamadığın edge case varsa söyle.

- `<sapma + gerekçe / "yok">`
- `<risk / "yok">`

## 📎 Hand-off Checklist (Dilara'ya teslim)
- [ ] Branch push'landı, PR açık (AB#id linkli)
- [ ] Bu Dev Work Summary Work Item'a attach
- [ ] Selector listesi eksiksiz
- [ ] Fixture ihtiyacı net
- [ ] Before/after screenshot ekli
