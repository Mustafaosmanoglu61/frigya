"""
Birleşik "ALL" profili senkronizasyonu — admin(1) + mustafa(6) → all@frigya.com

    cd webapp && python3 sync_all_profile.py

NE ZAMAN ÇALIŞTIRILIR
    Kaynak profillere (admin / mustafa) her yeni işlem veya nakit hareketi
    girildiğinde. Bu bir ANLIK KOPYADIR, canlı bağlantı DEĞİL — kaynaklar
    değişince ALL profili kendiliğinden güncellenmez, bayatlar.

NASIL ÇALIŞIR
    - Kaynak kullanıcılara DOKUNMAZ, sadece okur.
    - Hedef profilin verisi silinip sıfırdan kurulur (idempotent).
    - Portföyler isme göre birleşir: GeneralMu+GeneralMu, family+family.
    - Çakışan hedef/etiket/not değerlerinde öncelik admin'dedir; admin'de
      boş olan alanlar mustafa'daki değerle doldurulur.

DİKKAT — FIFO semantiği
    Birleşik profilde aynı portföy adı altındaki lotlar TEK havuz olur.
    Bu yüzden bir satış, diğer profilin daha eski lotunu tüketebilir ve
    ALL'ın gerçekleşen K/Z'si iki profilin toplamına EŞİT OLMAYABİLİR.
    Toplam maliyet korunur; fark yalnızca "tüketilen" ile "açık kalan"
    arasında yer değiştirir. Bu beklenen davranıştır, hata değildir.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database
import auth_service

TARGET_EMAIL = "all@frigya.com"
TARGET_PASSWORD = "1029384756"
TARGET_ROLE = "admin"

# Düşük öncelikliden yükseğe — sonra gelen çakışmayı kazanır
SRC = [(6, "mustafa"), (1, "admin")]
SRC_IDS = [u for u, _ in SRC]
LABEL = dict(SRC)


def main():
    with database.db() as conn:
        # ── 1. Hedef kullanıcı ──────────────────────────────────────────────
        row = conn.execute(
            "SELECT id FROM users WHERE email=?", (TARGET_EMAIL,)
        ).fetchone()

        if row:
            uid = row["id"]
            print(f"Mevcut hedef kullanıcı bulundu (id={uid}) — verisi temizleniyor")
            # ÖNEMLİ — silme sırası foreign key zincirini takip etmeli:
            # fifo_lot_matches → fifo_results/raw_transactions'a bağlı ve user_id
            # kolonu YOK; önce o temizlenmezse FK hatası alınır.
            conn.execute(
                """DELETE FROM fifo_lot_matches
                   WHERE fifo_result_id IN (SELECT id FROM fifo_results     WHERE user_id=?)
                      OR sell_tx_id     IN (SELECT id FROM raw_transactions WHERE user_id=?)
                      OR buy_tx_id      IN (SELECT id FROM raw_transactions WHERE user_id=?)""",
                (uid, uid, uid),
            )
            for t in ("fifo_results", "open_positions", "symbol_summary",
                      "raw_transactions", "cash_transactions", "watchlist",
                      "symbol_targets", "symbol_tags", "symbol_notes",
                      "portfolio_notes", "portfolios", "carry_forward_lots"):
                conn.execute(f"DELETE FROM {t} WHERE user_id=?", (uid,))
            conn.execute(
                "UPDATE users SET password_hash=?, role=?, is_active=1, "
                "approval_status='approved' WHERE id=?",
                (auth_service.hash_password(TARGET_PASSWORD), TARGET_ROLE, uid),
            )
        else:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, role, is_active, approval_status) "
                "VALUES (?,?,?,1,'approved')",
                (TARGET_EMAIL, auth_service.hash_password(TARGET_PASSWORD), TARGET_ROLE),
            )
            uid = cur.lastrowid
            print(f"Yeni kullanıcı oluşturuldu (id={uid})")

        q = lambda sql, p=(): conn.execute(sql, p).fetchall()
        ins = lambda sql, p: conn.execute(sql, p)

        # ── 2. Portföyler (isme göre birleşik; herhangi biri aktifse aktif) ──
        pf = {}
        for su in SRC_IDS:
            for r in q("SELECT name, description, is_active FROM portfolios WHERE user_id=?", (su,)):
                cur = pf.get(r["name"])
                pf[r["name"]] = {
                    "description": r["description"] or (cur or {}).get("description") or "",
                    "is_active": max(r["is_active"], (cur or {}).get("is_active", 0)),
                }
        # raw_transactions'ta olup portfolios tablosunda olmayanları da ekle
        for r in q(f"SELECT DISTINCT portfolio FROM raw_transactions WHERE user_id IN ({','.join('?'*len(SRC_IDS))})", tuple(SRC_IDS)):
            pf.setdefault(r["portfolio"], {"description": "", "is_active": 1})
        for name, v in pf.items():
            ins("INSERT INTO portfolios (user_id, name, description, is_active) VALUES (?,?,?,?)",
                (uid, name, v["description"], v["is_active"]))
        print(f"  portföyler      : {len(pf)}  {sorted(pf)}")

        # ── 3. raw_transactions — saf birleşim (çakışma yok, doğrulandı) ────
        n = 0
        for su in SRC_IDS:
            for r in q("SELECT tx_date, symbol, direction, quantity, price, total, "
                       "source_type, source_file, source_year, portfolio "
                       "FROM raw_transactions WHERE user_id=? ORDER BY tx_date, id", (su,)):
                ins("INSERT INTO raw_transactions (tx_date, symbol, direction, quantity, price, "
                    "total, source_type, source_file, source_year, portfolio, user_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (r["tx_date"], r["symbol"], r["direction"], r["quantity"], r["price"],
                     r["total"], r["source_type"], r["source_file"], r["source_year"],
                     r["portfolio"], uid))
                n += 1
        print(f"  raw_transactions: {n}")

        # ── 4. cash_transactions — birleşim + kaynak etiketi (virman izi) ───
        n = 0
        for su in SRC_IDS:
            for r in q("SELECT tx_date, portfolio, tx_type, amount, note "
                       "FROM cash_transactions WHERE user_id=? ORDER BY tx_date, id", (su,)):
                note = (r["note"] or "").strip()
                note = f"{note} [kaynak: {LABEL[su]}]" if note else f"[kaynak: {LABEL[su]}]"
                ins("INSERT INTO cash_transactions (user_id, portfolio, tx_date, tx_type, amount, note) "
                    "VALUES (?,?,?,?,?,?)",
                    (uid, r["portfolio"], r["tx_date"], r["tx_type"], r["amount"], note))
                n += 1
        print(f"  cash_transactions: {n}")

        # ── 5. watchlist — (portfolio,symbol) tekil; not boşsa alttan doldur ─
        wl = {}
        for su in SRC_IDS:
            for r in q("SELECT portfolio, symbol, notes, added_at FROM watchlist WHERE user_id=?", (su,)):
                k = (r["portfolio"].lower(), r["symbol"].upper())
                cur = wl.get(k, {})
                wl[k] = {
                    "portfolio": r["portfolio"], "symbol": r["symbol"],
                    "notes": r["notes"] or cur.get("notes"),
                    "added_at": min(x for x in (r["added_at"], cur.get("added_at")) if x),
                }
        for v in wl.values():
            ins("INSERT INTO watchlist (user_id, portfolio, symbol, notes, added_at) VALUES (?,?,?,?,?)",
                (uid, v["portfolio"], v["symbol"], v["notes"], v["added_at"]))
        print(f"  watchlist       : {len(wl)}")

        # ── 6. symbol_targets — alan bazlı birleşim (admin non-null kazanır) ─
        tg = {}
        for su in SRC_IDS:
            for r in q("SELECT portfolio, symbol, hedef_fiyat, taban_fiyat, "
                       "hedef_dolar_kazanci, stop_fiyat FROM symbol_targets WHERE user_id=?", (su,)):
                k = (r["portfolio"].lower(), r["symbol"].upper())
                cur = tg.get(k, {"portfolio": r["portfolio"], "symbol": r["symbol"]})
                for f in ("hedef_fiyat", "taban_fiyat", "hedef_dolar_kazanci", "stop_fiyat"):
                    if r[f] is not None:
                        cur[f] = r[f]
                    cur.setdefault(f, None)
                tg[k] = cur
        for v in tg.values():
            ins("INSERT INTO symbol_targets (user_id, portfolio, symbol, hedef_fiyat, "
                "taban_fiyat, hedef_dolar_kazanci, stop_fiyat) VALUES (?,?,?,?,?,?,?)",
                (uid, v["portfolio"], v["symbol"], v["hedef_fiyat"], v["taban_fiyat"],
                 v["hedef_dolar_kazanci"], v["stop_fiyat"]))
        print(f"  symbol_targets  : {len(tg)}")

        # ── 7. symbol_tags — sembol tekil, admin kazanır ─────────────────────
        tags = {}
        for su in SRC_IDS:
            for r in q("SELECT symbol, tag FROM symbol_tags WHERE user_id=?", (su,)):
                tags[r["symbol"].upper()] = (r["symbol"], r["tag"])
        for sym, tag in tags.values():
            ins("INSERT INTO symbol_tags (user_id, symbol, tag) VALUES (?,?,?)", (uid, sym, tag))
        print(f"  symbol_tags     : {len(tags)}")

        # ── 8. symbol_notes / portfolio_notes — tamamı kopyalanır ───────────
        n = 0
        for su in SRC_IDS:
            for r in q("SELECT symbol, note_text, created_at, updated_at FROM symbol_notes WHERE user_id=?", (su,)):
                ins("INSERT INTO symbol_notes (user_id, symbol, note_text, created_at, updated_at) "
                    "VALUES (?,?,?,?,?)", (uid, r["symbol"], r["note_text"], r["created_at"], r["updated_at"]))
                n += 1
        print(f"  symbol_notes    : {n}")

        n = 0
        for su in SRC_IDS:
            for r in q("SELECT portfolio, note_text, created_at, updated_at FROM portfolio_notes WHERE user_id=?", (su,)):
                ins("INSERT INTO portfolio_notes (user_id, portfolio, note_text, created_at, updated_at) "
                    "VALUES (?,?,?,?,?)", (uid, r["portfolio"], r["note_text"], r["created_at"], r["updated_at"]))
                n += 1
        print(f"  portfolio_notes : {n}")

        # ── 9. carry_forward_lots ───────────────────────────────────────────
        n = 0
        for su in SRC_IDS:
            for r in q("SELECT symbol, lot_date, quantity, price, cost, carry_into_year, notes "
                       "FROM carry_forward_lots WHERE user_id=?", (su,)):
                ins("INSERT INTO carry_forward_lots (symbol, lot_date, quantity, price, cost, "
                    "carry_into_year, notes, user_id) VALUES (?,?,?,?,?,?,?,?)",
                    (r["symbol"], r["lot_date"], r["quantity"], r["price"], r["cost"],
                     r["carry_into_year"], r["notes"], uid))
                n += 1
        print(f"  carry_lots      : {n}")

    # ── 10. FIFO yeniden hesapla (tüm kullanıcılar için türetilmiş tablolar) ─
    stats = database.recompute_fifo()
    print(f"\nFIFO yeniden hesaplandı: {stats}")
    return uid


if __name__ == "__main__":
    uid = main()
    print(f"\n✓ Birleşik profil hazır — user_id={uid}, email={TARGET_EMAIL}")
