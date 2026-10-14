"""Membaca dan menormalisasi berkas gudang, lalu menyimpannya ke SQLite.

Prinsip: nilai yang bisa dipastikan diseragamkan; nilai yang ambigu TIDAK ditebak,
melainkan diberi penanda (kolom `peringatan`) dan tetap menyimpan nilai aslinya.
Setiap baris menyimpan `sumber` (nama sheet + nomor baris Excel) agar bisa ditelusuri.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
MASTER_FILE = DATA_DIR / "Berkas_Gudang_Dari_Perusahaan.xlsx"
ENDSTOCK_FILE = DATA_DIR / "Catatan_Stok_Akhir_Agustus.xlsx"

DEFAULT_YEAR = 2026
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "agu": 8, "agt": 8, "ags": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}
UNIT_ALIASES = {"pack": "pak"}
CATEGORY_ALIASES = {"elektrikal": "Elektrik"}


# ---------------------------------------------------------------- helpers
def _blank(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def parse_qty(raw):
    """Kembalikan (angka | None, peringatan | None). Tidak menebak nilai yang tidak jelas."""
    if _blank(raw):
        return None, "kosong"
    if isinstance(raw, (int, float)):
        return int(raw) if float(raw).is_integer() else float(raw), None
    text = str(raw).strip()
    if text in {"?", "-"}:
        return None, "tidak diketahui"
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None, "bukan angka"
    number = float(match.group().replace(",", "."))
    number = int(number) if number.is_integer() else number
    if re.search(r"sekitar|kira|perkiraan|±|~", text.lower()):
        return number, "perkiraan"
    if re.fullmatch(r"\d+", text):
        return number, None
    return number, "angka ditulis bersama teks"


def parse_date(raw, default_year: int = DEFAULT_YEAR):
    """Kembalikan (date | None, peringatan | None). Urutan numerik dibaca hari/bulan/tahun."""
    if _blank(raw):
        return None, "kosong"
    if isinstance(raw, datetime):
        return raw.date(), None
    if isinstance(raw, date):
        return raw, None
    text = str(raw).strip().lower()
    try:
        m = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
        if m:
            return date(int(m[1]), int(m[2]), int(m[3])), None
        m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
        if m:
            year = int(m[3])
            return date(year + 2000 if year < 100 else year, int(m[2]), int(m[1])), None
        m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\.?\s*(\d{4})?", text)
        if m and m[2][:3] in MONTHS:
            year = int(m[3]) if m[3] else default_year
            note = None if m[3] else f"tahun diasumsikan {default_year}"
            return date(year, MONTHS[m[2][:3]], int(m[1])), note
    except ValueError:
        pass
    return None, "tanggal tidak dapat dibaca"


def name_key(name) -> str:
    """Bentuk seragam nama barang untuk membandingkan penulisan yang berbeda."""
    s = str(name or "").lower()
    s = re.sub(r"(\d+)\s*(?:meter|m)\b", r"\1m", s)
    s = re.sub(r"(\d+)\s*(?:watt|w)\b", r"\1w", s)
    s = re.sub(r"(\d+)\s*ml\b", r"\1ml", s)
    s = re.sub(r"\bukuran\b", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


def loc_key(location) -> str:
    """'Rak A-1', 'A-1', 'A1' -> 'A1'; 'Gudang belakang' / 'belakang' -> 'BELAKANG'."""
    s = re.sub(r"\b(?:rak|gudang)\b", " ", str(location or "").lower())
    m = re.fullmatch(r"\s*([a-z])\s*-?\s*0*(\d+)\s*", s)
    if m:
        return f"{m[1].upper()}{int(m[2])}"
    return " ".join(s.split()).upper()


def norm_unit(unit):
    if _blank(unit):
        return None
    u = str(unit).strip().lower()
    return UNIT_ALIASES.get(u, u)


def norm_code(code):
    if _blank(code):
        return None
    return str(code).strip().upper()


def _text(value):
    return None if _blank(value) else str(value).strip()


def _join(flags):
    return "; ".join(str(f) for f in flags if not _blank(f)) or None


def _read(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, dtype=object)
    df["_baris"] = df.index + 2  # baris Excel (baris 1 = judul kolom)
    return df


# ---------------------------------------------------------------- loaders
def load_items(path: Path = MASTER_FILE) -> pd.DataFrame:
    rows = []
    for r in _read(path, "Stok Barang").itertuples(index=False):
        kode, nama, kategori, satuan, lokasi, stok, minimum, catatan, baris = r
        num, flag = parse_qty(stok)
        kat = _text(kategori)
        kat_norm = CATEGORY_ALIASES.get(kat.lower(), kat.title()) if kat else None
        rows.append({
            "kode": norm_code(kode), "nama": _text(nama), "kategori": kat_norm,
            "satuan": norm_unit(satuan), "satuan_asli": _text(satuan),
            "lokasi": _text(lokasi), "lokasi_key": loc_key(lokasi),
            "stok_raw": _text(stok), "stok_num": num, "stok_flag": flag,
            "min_stok": parse_qty(minimum)[0], "catatan": _text(catatan),
            "name_key": name_key(nama), "sumber": f"Stok Barang, baris {baris}",
        })
    return pd.DataFrame(rows)


def load_end_stock(path: Path = ENDSTOCK_FILE) -> pd.DataFrame:
    rows = []
    for r in _read(path, "Stok per 31 Agustus").itertuples(index=False):
        kode, nama, lokasi, qty, update, pic, baris = r
        num, flag = parse_qty(qty)
        tgl, tflag = parse_date(update)
        rows.append({
            "kode": norm_code(kode), "nama": _text(nama), "lokasi": _text(lokasi),
            "qty_raw": _text(qty), "qty_num": num, "qty_flag": flag,
            "update_raw": _text(update), "update_date": tgl.isoformat() if tgl else None,
            "update_flag": tflag, "pic": _text(pic),
            "sumber": f"Stok per 31 Agustus, baris {baris}",
        })
    return pd.DataFrame(rows)


def _load_movements(path: Path, sheet: str, kind: str) -> pd.DataFrame:
    rows = []
    df = _read(path, sheet)
    for r in df.itertuples(index=False):
        tgl_raw, bukti, kode, nama, qty, satuan, pihak, petugas = r[:8]
        if kind == "masuk":
            lokasi, catatan, status = r[8], r[9], None
        else:  # keluar: kolom ke-9 = status, ke-10 = catatan
            lokasi, status, catatan = None, r[8], r[9]
        baris = r[-1]
        tgl, tflag = parse_date(tgl_raw)
        num, qflag = parse_qty(qty)
        flags = [
            f"tanggal: {tflag}" if tflag else None,
            f"jumlah: {qflag}" if qflag else None,
            "tanpa kode barang" if _blank(kode) else None,
            "tanpa nomor bukti" if _blank(bukti) or str(bukti).strip() == "-" else None,
            "satuan kosong" if _blank(satuan) else None,
        ]
        if kind == "keluar" and status and "belum" in str(status).lower():
            flags.append(f"status: {status}")
        rows.append({
            "jenis": kind, "tgl_raw": _text(tgl_raw), "tgl": tgl.isoformat() if tgl else None,
            "bukti": _text(bukti), "kode": norm_code(kode), "nama": _text(nama),
            "qty_raw": _text(qty), "qty_num": num, "satuan": norm_unit(satuan),
            "pihak": _text(pihak), "petugas": _text(petugas), "lokasi": _text(lokasi),
            "status": _text(status), "catatan": _text(catatan), "name_key": name_key(nama),
            "dup": 0, "peringatan": _join(flags), "sumber": f"{sheet}, baris {baris}",
        })
    out = pd.DataFrame(rows)
    # Tandai kemungkinan duplikat: bukti + kode + jumlah sama dengan baris sebelumnya.
    seen: dict[tuple, str] = {}
    for i, row in out.iterrows():
        if row["bukti"] in (None, "-"):
            continue
        key = (row["bukti"], row["kode"], row["qty_num"])
        if key in seen:
            out.at[i, "dup"] = 1
            note = f"kemungkinan duplikat dari {seen[key]}"
            out.at[i, "peringatan"] = _join([out.at[i, "peringatan"], note])
        else:
            seen[key] = row["sumber"]
    return out


def load_wa_notes(path: Path = MASTER_FILE) -> pd.DataFrame:
    rows = []
    for r in _read(path, "Catatan WA").itertuples(index=False):
        tgl_raw, pengirim, pesan, baris = r
        tgl, _ = parse_date(tgl_raw)
        rows.append({
            "tgl": tgl.isoformat() if tgl else None, "pengirim": _text(pengirim),
            "pesan": _text(pesan), "sumber": f"Catatan WA, baris {baris}",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- database
def build_database() -> sqlite3.Connection:
    """Bangun ulang SQLite (di memori) dari berkas Excel setiap aplikasi dijalankan.

    Dibangun ulang, bukan disimpan sebagai file, supaya aplikasi tetap benar pada platform
    yang menghapus file lokal saat restart.
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    load_items().to_sql("items", conn, index=False)
    load_end_stock().to_sql("stock_end", conn, index=False)
    movements = pd.concat(
        [_load_movements(MASTER_FILE, "Barang Masuk", "masuk"),
         _load_movements(MASTER_FILE, "Barang Keluar", "keluar")],
        ignore_index=True,
    )
    movements.to_sql("movements", conn, index=False)
    load_wa_notes().to_sql("wa_notes", conn, index=False)
    return conn
