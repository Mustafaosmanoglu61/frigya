"""
frigya_core.yazma — DB yazma fonksiyonları (skill yazma/*.py'den port).

hedef_guncelle(...)  → taktiksel hedef/taban/stop (apply ile yazar)
analist_hedef(...)   → uzun vade analyst range (high→hedef, low→taban; stop dokunulmaz)

Her ikisi de apply=False iken dry-run: before/after/changes döner, YAZMAZ.
"""
from datetime import datetime


def hedef_guncelle(conn, user_id, symbol, portfolio, hedef=None, taban=None, stop=None,
                   hedef_dolar=None, clear_hedef=False, clear_taban=False, clear_stop=False,
                   note=None, apply=False):
    sym = symbol.upper()

    before = conn.execute(
        """SELECT hedef_fiyat, taban_fiyat, stop_fiyat, hedef_dolar_kazanci, updated_at
           FROM symbol_targets WHERE user_id = ? AND portfolio = ? AND symbol = ?""",
        (user_id, portfolio, sym),
    ).fetchone()
    before_dict = dict(before) if before else None

    def resolve(new_val, clear_flag, before_key):
        if clear_flag:
            return None
        if new_val is not None:
            return new_val
        return before_dict.get(before_key) if before_dict else None

    after_hedef = resolve(hedef, clear_hedef, "hedef_fiyat")
    after_taban = resolve(taban, clear_taban, "taban_fiyat")
    after_stop = resolve(stop, clear_stop, "stop_fiyat")
    after_hedef_dolar = hedef_dolar if hedef_dolar is not None else (
        before_dict.get("hedef_dolar_kazanci") if before_dict else None)

    changes = {}
    if not before_dict:
        changes["_status"] = "yeni kayıt oluşturulacak"
    else:
        for label, b, a in [
            ("hedef_fiyat", before_dict.get("hedef_fiyat"), after_hedef),
            ("taban_fiyat", before_dict.get("taban_fiyat"), after_taban),
            ("stop_fiyat", before_dict.get("stop_fiyat"), after_stop),
            ("hedef_dolar_kazanci", before_dict.get("hedef_dolar_kazanci"), after_hedef_dolar),
        ]:
            if b != a:
                changes[label] = {"before": b, "after": a}

    plan = {
        "symbol": sym, "portfolio": portfolio, "user_id": user_id,
        "before": before_dict,
        "after": {"hedef_fiyat": after_hedef, "taban_fiyat": after_taban,
                  "stop_fiyat": after_stop, "hedef_dolar_kazanci": after_hedef_dolar},
        "changes": changes, "note_will_be_added": bool(note), "apply": apply,
    }

    if not apply:
        plan["_status"] = "DRY RUN — değişiklik yapılmadı"
        return plan

    if not changes and not note:
        plan["_status"] = "değişiklik yok, yazma atlandı"
        return plan

    with conn:
        conn.execute(
            """INSERT INTO symbol_targets
                   (user_id, portfolio, symbol, hedef_fiyat, taban_fiyat,
                    hedef_dolar_kazanci, stop_fiyat, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, portfolio, symbol) DO UPDATE SET
                   hedef_fiyat = excluded.hedef_fiyat,
                   taban_fiyat = excluded.taban_fiyat,
                   hedef_dolar_kazanci = excluded.hedef_dolar_kazanci,
                   stop_fiyat = excluded.stop_fiyat,
                   updated_at = datetime('now')""",
            (user_id, portfolio, sym, after_hedef, after_taban, after_hedef_dolar, after_stop),
        )
        if note:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            parts = [f"{k}: {v['before']}→{v['after']}" for k, v in changes.items() if not k.startswith("_")]
            change_summary = "; ".join(parts) if parts else "(seviye değişikliği yok)"
            full_text = f"[{stamp} · {portfolio}] {note}\n→ {change_summary}"
            conn.execute(
                "INSERT INTO symbol_notes (user_id, symbol, note_text) VALUES (?, ?, ?)",
                (user_id, sym, full_text),
            )
            plan["note_added"] = full_text

    plan["_status"] = "yazıldı"
    return plan


def analist_hedef(conn, user_id, symbol, portfolio, low=None, high=None, avg=None,
                  source="manuel", analyst=None, target_date=None, apply=False, no_note=False):
    sym = symbol.upper()
    if low is None and high is None:
        return {"error": True, "message": "Manuel mod için low ve/veya high vermelisin."}

    before = conn.execute(
        """SELECT hedef_fiyat, taban_fiyat, stop_fiyat, hedef_dolar_kazanci, updated_at
           FROM symbol_targets WHERE user_id = ? AND portfolio = ? AND symbol = ?""",
        (user_id, portfolio, sym),
    ).fetchone()
    before_dict = dict(before) if before else None

    new_hedef = high if high is not None else (before_dict.get("hedef_fiyat") if before_dict else None)
    new_taban = low if low is not None else (before_dict.get("taban_fiyat") if before_dict else None)
    new_stop = before_dict.get("stop_fiyat") if before_dict else None
    new_dolar = before_dict.get("hedef_dolar_kazanci") if before_dict else None

    changes = {}
    if not before_dict:
        changes["_status"] = "yeni kayıt"
    else:
        if before_dict.get("hedef_fiyat") != new_hedef:
            changes["hedef_fiyat (high)"] = {"before": before_dict.get("hedef_fiyat"), "after": new_hedef}
        if before_dict.get("taban_fiyat") != new_taban:
            changes["taban_fiyat (low)"] = {"before": before_dict.get("taban_fiyat"), "after": new_taban}

    plan = {
        "symbol": sym, "portfolio": portfolio, "user_id": user_id, "source": source,
        "analyst": analyst, "target_date": target_date,
        "input": {"high (→ hedef_fiyat)": high, "low  (→ taban_fiyat)": low, "avg (bilgi)": avg},
        "before": before_dict,
        "after": {"hedef_fiyat": new_hedef, "taban_fiyat": new_taban,
                  "stop_fiyat": new_stop, "hedef_dolar_kazanci": new_dolar},
        "changes": changes, "stop_korundu": True, "apply": apply,
    }

    if not apply:
        plan["_status"] = "DRY RUN — yazma yapılmadı (apply=true ile uygula)"
        return plan
    if not changes:
        plan["_status"] = "değişiklik yok, yazma atlandı"
        return plan

    with conn:
        conn.execute(
            """INSERT INTO symbol_targets
                   (user_id, portfolio, symbol, hedef_fiyat, taban_fiyat,
                    hedef_dolar_kazanci, stop_fiyat, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id, portfolio, symbol) DO UPDATE SET
                   hedef_fiyat = excluded.hedef_fiyat,
                   taban_fiyat = excluded.taban_fiyat,
                   updated_at = datetime('now')""",
            (user_id, portfolio, sym, new_hedef, new_taban, new_dolar, new_stop),
        )
        if not no_note:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            parts = []
            if low is not None:  parts.append(f"low={low}")
            if high is not None: parts.append(f"high={high}")
            if avg is not None:  parts.append(f"avg={avg}")
            analyst_str = f" · analist: {analyst}" if analyst else ""
            tdate_str = f" · vade: {target_date}" if target_date else ""
            note_text = (
                f"[{stamp} · {portfolio} · analyst-range] "
                f"Uzun vade fiyat aralığı güncellendi: {', '.join(parts)}. "
                f"Kaynak: {source}{analyst_str}{tdate_str}. "
                f"(taban_fiyat ↔ hedef_fiyat olarak yazıldı; stop_fiyat korundu.)"
            )
            conn.execute(
                "INSERT INTO symbol_notes (user_id, symbol, note_text) VALUES (?, ?, ?)",
                (user_id, sym, note_text),
            )
            plan["note_added"] = note_text

    plan["_status"] = "yazıldı"
    return plan
