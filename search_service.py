"""Pencarian barang berbasis aturan: kode, nama (toleran penulisan), lokasi, dan beberapa pertanyaan umum.

Aturan utama: tampilkan kandidat + sumber + peringatan. Jangan menggabungkan kode yang berbeda
dan jangan menganggap satu angka stok sebagai pasti bila sumbernya berbeda atau tidak jelas.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import pandas as pd

from data_processing import loc_key, name_key

STOPWORDS = {"stok", "stock", "barang", "cari", "berapa", "sisa", "jumlah", "ada", "apa",
             "info", "informasi", "tolong", "dong", "yang", "di", "dan", "untuk", "lokasi"}
THRESHOLD = 0.6
MAX_CANDIDATES = 5
NOTE_WORDS = ("perlu", "belum", "perkiraan", "kemungkinan", "duplikat", "copy", "cek", "?")


@dataclass
class Candidate:
    kode: str | None
    nama: str
    kategori: str | None
    satuan: str | None
    lokasi: str | None
    score: float
    reason: str
    stock_values: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    similar: list[dict] = field(default_factory=list)
    transactions: pd.DataFrame = field(default_factory=pd.DataFrame)
    summary: dict = field(default_factory=dict)
    wa_notes: list[dict] = field(default_factory=list)


@dataclass
class SearchResult:
    query: str
    status: str  # ok | not_found | empty | listing
    message: str = ""
    candidates: list[Candidate] = field(default_factory=list)
    listing: pd.DataFrame | None = None
    listing_title: str = ""
    suggestions: list[str] = field(default_factory=list)


# ------------------------------------------------------------ data access
def _read(conn, sql: str, params=()) -> pd.DataFrame:
    """read_sql dengan nilai kosong sebagai None (bukan NaN) agar mudah diperiksa."""
    df = pd.read_sql(sql, conn, params=params)
    return df.astype(object).where(df.notna(), None)


def _items(conn) -> pd.DataFrame:
    return _read(conn, "SELECT * FROM items")


def _fmt(value):
    return "—" if value is None or (isinstance(value, float) and pd.isna(value)) else value


def _n(x):
    """Angka tampil tanpa '.0' bila bilangan bulat."""
    return int(x) if isinstance(x, float) and x.is_integer() else x


def _tokens(key: str) -> set[str]:
    return {t for t in key.split() if t not in STOPWORDS}


def _similar_items(row, items: pd.DataFrame) -> list[dict]:
    """Barang lain dengan nama yang kemungkinan sama. Hanya diberi tanda, tidak digabung."""
    out = []
    mine = _tokens(row["name_key"])
    for _, other in items.iterrows():
        if other["kode"] == row["kode"]:
            continue
        theirs = _tokens(other["name_key"])
        if other["name_key"] == row["name_key"]:
            reason = "nama identik setelah penulisan diseragamkan"
        elif len(mine) >= 2 and len(theirs) >= 2 and (mine < theirs or theirs < mine):
            reason = "nama mirip (salah satu lebih singkat)"
        else:
            continue
        out.append({"kode": other["kode"], "nama": other["nama"], "lokasi": other["lokasi"],
                    "stok": other["stok_raw"], "stok_num": other["stok_num"], "alasan": reason})
    return out


def _total(df):
    total = pd.to_numeric(df["qty_num"]).sum(min_count=1)
    return None if pd.isna(total) else _n(float(total))


# ------------------------------------------------------------ candidate building
def build_candidate(conn: sqlite3.Connection, row, score: float, reason: str,
                    items: pd.DataFrame | None = None) -> Candidate:
    items = _items(conn) if items is None else items
    kode = row["kode"]
    c = Candidate(kode=kode, nama=row["nama"], kategori=row["kategori"], satuan=row["satuan"],
                  lokasi=row["lokasi"], score=score, reason=reason)

    # --- nilai stok per sumber
    c.stock_values.append({"Sumber": "Stok Barang (master)", "Nilai asli": _fmt(row["stok_raw"]),
                           "Angka terbaca": _fmt(_n(row["stok_num"])), "Catatan": row["stok_flag"] or "",
                           "Rujukan": row["sumber"]})
    end = _read(conn, "SELECT * FROM stock_end WHERE kode = ?", (kode,))
    for _, e in end.iterrows():
        note = "; ".join(x for x in [e["qty_flag"], f"update: {e['update_raw']}" if e["update_raw"] else None,
                                     f"PIC {e['pic']}" if e["pic"] else None] if x)
        c.stock_values.append({"Sumber": "Catatan stok akhir", "Nilai asli": _fmt(e["qty_raw"]),
                               "Angka terbaca": _fmt(_n(e["qty_num"])), "Catatan": note, "Rujukan": e["sumber"]})
        if e["update_flag"] and e["update_flag"] != "kosong":
            c.warnings.append(f"Tanggal update pada catatan stok akhir tidak jelas ('{e['update_raw']}').")

    # --- peringatan stok
    nums = [v["Angka terbaca"] for v in c.stock_values if v["Angka terbaca"] != "—"]
    if len(set(nums)) > 1:
        c.warnings.append("Angka stok berbeda antar sumber — perlu verifikasi, jangan dianggap pasti.")
    if row["stok_num"] is None or pd.isna(row["stok_num"]):
        c.warnings.append("Stok pada master kosong atau tidak jelas; tidak ada angka yang bisa dipastikan.")
    for v in c.stock_values:
        if v["Catatan"] and ("perkiraan" in v["Catatan"] or "tidak diketahui" in v["Catatan"]):
            c.warnings.append(f"{v['Sumber']}: nilai '{v['Nilai asli']}' bersifat {v['Catatan'].split(';')[0]}.")
    if row["catatan"] and any(w in row["catatan"].lower() for w in NOTE_WORDS):
        c.warnings.append(f"Catatan pada data: \"{row['catatan']}\"")
    if pd.notna(row["stok_num"]) and pd.notna(row["min_stok"]) and row["stok_num"] < row["min_stok"]:
        c.warnings.append(f"Stok tercatat ({_n(row['stok_num'])}) di bawah minimum ({_n(row['min_stok'])}).")

    # --- barang serupa (tidak digabung)
    c.similar = _similar_items(row, items)
    for s in c.similar:
        if pd.notna(row["stok_num"]) and s["stok_num"] is not None and pd.notna(s["stok_num"]):
            if row["stok_num"] != s["stok_num"]:
                c.warnings.append(
                    f"Kemungkinan barang yang sama dengan {s['kode']} ({s['nama']}) tetapi angka stok berbeda "
                    f"({_n(row['stok_num'])} vs {_n(s['stok_num'])}). Jangan dijumlahkan atau digabung tanpa verifikasi.")
            else:
                c.warnings.append(
                    f"{s['kode']} ({s['nama']}) tampak sama dan angkanya identik ({_n(row['stok_num'])}); "
                    "bisa jadi salinan data, bukan stok ganda — perlu verifikasi.")
        else:
            c.warnings.append(f"Kemungkinan barang yang sama dengan {s['kode']} ({s['nama']}); "
                              "kodenya berbeda dan belum diverifikasi.")

    # --- transaksi: cocok kode, atau tanpa kode tapi nama cocok (diberi peringatan)
    mv = _read(conn, "SELECT * FROM movements")
    by_code = mv[mv["kode"] == kode].copy()
    mine = _tokens(row["name_key"])
    nocode = mv[mv["kode"].isna()].copy()
    nocode = nocode[nocode["name_key"].map(lambda k: bool(_tokens(k)) and _tokens(k) <= mine)]
    if not nocode.empty:
        nocode["peringatan"] = nocode["peringatan"].fillna("") + "; dicocokkan lewat nama, bisa milik barang lain dengan nama serupa"
    tx = pd.concat([by_code, nocode]).sort_values(["tgl", "sumber"], na_position="last")
    c.transactions = tx
    masuk = tx[(tx["jenis"] == "masuk") & (tx["dup"] == 0) & tx["kode"].notna()]
    keluar = tx[(tx["jenis"] == "keluar") & tx["kode"].notna()]
    c.summary = {
        "masuk": _total(masuk), "keluar": _total(keluar),
        "dup_masuk": int(((tx["jenis"] == "masuk") & (tx["dup"] == 1)).sum()),
        "tanpa_angka": int(tx["qty_num"].isna().sum()),
        "tanpa_kode": int(tx["kode"].isna().sum()),
    }
    if c.summary["dup_masuk"]:
        c.warnings.append(f"{c.summary['dup_masuk']} baris barang masuk ditandai kemungkinan duplikat dan tidak dihitung pada total.")
    if c.summary["tanpa_kode"]:
        c.warnings.append(f"{c.summary['tanpa_kode']} transaksi tanpa kode dicocokkan lewat nama dan tidak dihitung pada total.")

    # --- catatan WhatsApp terkait
    notes = _read(conn, "SELECT * FROM wa_notes")
    buktis = {b.lower() for b in by_code["bukti"].dropna() if re.search(r"\d", b)}
    head = next(iter(row["name_key"].split()), "")
    for _, n in notes.iterrows():
        msg = n["pesan"].lower()
        why = None
        if kode and kode.lower() in msg:
            why = "menyebut kode barang"
        elif any(b in msg for b in buktis):
            why = "menyebut nomor PO/bukti"
        elif row["name_key"] and row["name_key"] in name_key(msg):
            why = "menyebut nama barang"
        elif head and re.search(rf"\b{re.escape(head)}\b", msg):
            why = "menyebut kata utama nama barang (kurang pasti)"
        if why:
            c.wa_notes.append({"Tanggal": n["tgl"], "Pengirim": n["pengirim"], "Pesan": n["pesan"],
                               "Mengapa terkait": why, "Rujukan": n["sumber"]})
    return c


# ------------------------------------------------------------ scoring
def _score_name(qkey: str, ikey: str) -> tuple[float, str]:
    qt, it = _tokens(qkey), _tokens(ikey)
    if qkey == ikey:
        return 1.0, "nama sama persis"
    if qkey and (qkey in ikey or ikey in qkey):
        return 0.9, "nama mengandung kata kunci"
    if qt and qt <= it:
        return 0.85, "semua kata kunci ditemukan pada nama"
    ratio = SequenceMatcher(None, qkey, ikey).ratio()
    overlap = len(qt & it) / len(qt) if qt else 0
    score = max(ratio * 0.9, overlap * 0.8)
    return score, "nama mirip (toleran salah ketik/penulisan)"


def _lookup_by_code(conn, query: str, items: pd.DataFrame) -> SearchResult | None:
    m = re.search(r"\bbrg\s*-?\s*0*(\d+)\b", query.lower())
    if not m:
        return None
    kode = f"BRG{int(m[1]):03d}"
    hit = items[items["kode"] == kode]
    if hit.empty:
        return SearchResult(query, "not_found", message=(
            f"Data untuk kode {kode} tidak ditemukan pada sumber yang tersedia. "
            "Ini tidak berarti barangnya tidak ada secara fisik — periksa kode atau coba nama barang."))
    return SearchResult(query, "ok", candidates=[build_candidate(conn, hit.iloc[0], 1.0, "kode sama persis", items)])


def _listing_low_stock(conn, query, items) -> SearchResult:
    known = items[items["stok_num"].notna() & items["min_stok"].notna()]
    low = known[known["stok_num"] < known["min_stok"]]
    unknown = items[items["stok_num"].isna()]
    parts = [low.assign(Status="di bawah minimum")[["kode", "nama", "stok_raw", "min_stok", "Status"]],
             unknown.assign(Status="stok tidak jelas — tidak bisa dinilai")[["kode", "nama", "stok_raw", "min_stok", "Status"]]]
    table = pd.concat(parts).rename(columns={"kode": "Kode", "nama": "Nama", "stok_raw": "Stok tercatat", "min_stok": "Min. stok"})
    msg = (f"{len(low)} barang tercatat di bawah minimum dan {len(unknown)} barang stoknya tidak bisa dinilai "
           "(kosong). Angka mengikuti master 'Stok Barang' dan belum diverifikasi fisik.")
    return SearchResult(query, "listing", message=msg, listing=table.reset_index(drop=True),
                        listing_title="Stok di bawah minimum / tidak jelas")


def _listing_issues(conn, query, items) -> SearchResult:
    rows = []
    for _, r in items.iterrows():
        cand = build_candidate(conn, r, 1.0, "", items)
        if cand.warnings:
            rows.append({"Kode": cand.kode, "Nama": cand.nama, "Jumlah peringatan": len(cand.warnings),
                         "Peringatan pertama": cand.warnings[0]})
    table = pd.DataFrame(rows).sort_values("Jumlah peringatan", ascending=False).reset_index(drop=True)
    return SearchResult(query, "listing", message=f"{len(table)} dari {len(items)} barang memiliki peringatan data.",
                        listing=table, listing_title="Barang dengan data perlu verifikasi")


def search_items(conn: sqlite3.Connection, query: str) -> SearchResult:
    query = (query or "").strip()
    if not query:
        return SearchResult(query, "empty", message="Masukkan nama atau kode barang.")
    items = _items(conn)
    q = query.lower()

    if re.search(r"menipis|di bawah min|dibawah min|stok rendah|kurang dari min", q):
        return _listing_low_stock(conn, query, items)
    if re.search(r"tidak lengkap|perlu verifikasi|bermasalah|konflik|duplikat|tidak konsisten", q):
        return _listing_issues(conn, query, items)

    by_code = _lookup_by_code(conn, query, items)
    if by_code:
        return by_code

    qkey = name_key(query)
    scored = []
    qloc = loc_key(query)
    for _, r in items.iterrows():
        score, reason = _score_name(qkey, r["name_key"])
        if qloc and qloc == r["lokasi_key"] and re.fullmatch(r"[A-Z]\d+|BELAKANG", qloc):
            score, reason = max((score, reason), (0.8, "lokasi rak sama"))
        if score >= THRESHOLD:
            scored.append((score, reason, r))
    scored.sort(key=lambda t: (-t[0], t[2]["kode"]))
    if not scored:
        near = sorted(((SequenceMatcher(None, qkey, r["name_key"]).ratio(), r["nama"]) for _, r in items.iterrows()), reverse=True)
        sugg = [n for s, n in near[:3] if s >= 0.45]
        return SearchResult(query, "not_found", suggestions=sugg, message=(
            f"Data untuk '{query}' tidak ditemukan pada sumber yang tersedia. Ini tidak berarti barangnya tidak ada "
            "secara fisik — periksa ejaan atau coba kata kunci lain."))
    cands = [build_candidate(conn, r, s, why, items) for s, why, r in scored[:MAX_CANDIDATES]]
    msg = f"{len(cands)} kandidat ditemukan." + (" Beberapa kandidat bisa jadi barang yang sama — bandingkan sebelum memilih." if len(cands) > 1 else "")
    return SearchResult(query, "ok", message=msg, candidates=cands)


def merge_by_names(conn: sqlite3.Connection, query: str, names: list[str]) -> SearchResult | None:
    """Jalankan pencarian biasa untuk nama barang hasil pemahaman AI, lalu gabungkan kandidatnya (unik per kode).

    Kandidat tetap berasal dari data; AI hanya memilih nama yang SUDAH ada pada data.
    """
    seen: dict[str, Candidate] = {}
    for name in names:
        res = search_items(conn, name)
        if res.status != "ok":
            continue
        for c in res.candidates:
            if c.kode in seen or c.score < 0.9:   # hanya kecocokan nama kuat
                continue
            c.reason = f"{c.reason}; kata kunci '{query}' dipahami AI sebagai '{name}'"
            seen[c.kode] = c
    cands = list(seen.values())[:MAX_CANDIDATES]
    if not cands:
        return None
    msg = (f"{len(cands)} kandidat ditemukan lewat pemahaman AI atas kata kunci '{query}'. "
           "Periksa apakah kandidat sesuai dengan yang Anda maksud.")
    return SearchResult(query, "ok", message=msg, candidates=cands)
