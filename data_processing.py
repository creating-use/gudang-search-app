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
ENDSTOCK_FILE = DATA_DIR / "Catatan_Stok_Akhir.xlsx"  # sheet pertama dibaca, apa pun namanya

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


class DataFileError(Exception):
    """Berkas data tidak bisa dibaca (berkas/sheet/kolom wajib hilang). Pesannya aman ditampilkan ke pengguna."""


def _hkey(header) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(header).lower()).strip()


# Kolom dikenali dari NAMA header (bukan urutan), jadi kolom boleh ditambah atau diurutkan ulang.
# Format: nama_logis: ([nama header yang dikenali], wajib?)
SPECS = {
    "items": {"kode": (["kode barang", "kode"], True), "nama": (["nama barang", "barang", "nama"], True),
              "kategori": (["kategori"], False), "satuan": (["satuan", "unit"], False),
              "lokasi": (["lokasi"], False), "stok": (["stok tercatat", "stok", "qty"], True),
              "minimum": (["min stok", "minimum", "stok minimum"], False), "catatan": (["catatan"], False)},
    "masuk": {"tgl": (["tgl", "tanggal", "tanggal masuk"], True), "bukti": (["no bukti po", "no bukti", "bukti", "no po"], False),
              "kode": (["kode barang", "kode"], True), "nama": (["nama barang", "barang", "nama"], False),
              "qty": (["qty masuk", "jumlah masuk", "qty", "jumlah"], True), "satuan": (["satuan", "unit"], False),
              "pihak": (["supplier", "pemasok"], False), "petugas": (["diterima oleh", "petugas"], False),
              "lokasi": (["lokasi taruh", "lokasi"], False), "catatan": (["catatan"], False)},
    "keluar": {"tgl": (["tanggal keluar", "tgl keluar", "tgl", "tanggal"], True),
               "bukti": (["no surat jalan", "surat jalan", "no sj", "no bukti"], False),
               "kode": (["kode barang", "kode"], True), "nama": (["barang", "nama barang", "nama"], False),
               "qty": (["jumlah keluar", "qty keluar", "qty", "jumlah"], True), "satuan": (["unit", "satuan"], False),
               "pihak": (["tujuan pemesan", "tujuan", "pemesan"], False), "petugas": (["diambil oleh", "petugas"], False),
               "status": (["status"], False), "catatan": (["catatan"], False)},
    "wa": {"tgl": (["tanggal", "tgl"], True), "pengirim": (["pengirim"], False), "pesan": (["pesan catatan", "pesan", "catatan"], True)},
    "endstock": {"kode": (["kode barang", "kode"], True), "nama": (["nama barang", "nama"], False),
                 "lokasi": (["lokasi"], False), "qty": (["qty menurut catatan", "qty", "jumlah", "stok"], True),
                 "update": (["update terakhir", "update", "tanggal update"], False), "pic": (["pic", "penanggung jawab"], False)},
}


def _read(path: Path, sheet: str | None, spec: str) -> tuple[pd.DataFrame, str]:
    """Baca satu sheet berdasarkan nama header. Kembalikan (data, nama sheet asli).

    sheet=None -> pakai sheet pertama. Baris yang seluruhnya kosong dilewati, nomor baris Excel tetap benar.
    """
    if not Path(path).exists():
        raise DataFileError(f"Berkas data '{Path(path).name}' tidak ditemukan di folder data/.")
    try:
        xl = pd.ExcelFile(path)
    except Exception as exc:  # berkas rusak / bukan xlsx
        raise DataFileError(f"Berkas '{Path(path).name}' tidak bisa dibuka sebagai Excel ({type(exc).__name__}).") from None
    if sheet is None:
        actual = xl.sheet_names[0]
    else:
        match = [n for n in xl.sheet_names if _hkey(n) == _hkey(sheet)]
        if not match:
            raise DataFileError(f"Sheet '{sheet}' tidak ditemukan pada '{Path(path).name}'. Sheet yang ada: {', '.join(xl.sheet_names)}.")
        actual = match[0]
    raw = xl.parse(actual, dtype=object)
    by_key = {_hkey(c): c for c in raw.columns}
    out = pd.DataFrame(index=raw.index)
    missing = []
    for logical, (aliases, required) in SPECS[spec].items():
        col = next((by_key[a] for a in aliases if a in by_key), None)
        if col is None:
            out[logical] = None
            if required:
                missing.append(f"{aliases[0]}")
        else:
            out[logical] = raw[col]
    if missing:
        raise DataFileError(f"Sheet '{actual}' pada '{Path(path).name}' tidak memiliki kolom wajib: {', '.join(missing)}. "
                            f"Kolom yang terbaca: {', '.join(map(str, raw.columns))}.")
    out["_baris"] = raw.index + 2  # baris Excel (baris 1 = judul kolom)
    keep = out.drop(columns="_baris").apply(lambda r: any(not _blank(v) for v in r), axis=1)
    return out[keep].astype(object).where(out[keep].notna(), None), actual


# ---------------------------------------------------------------- loaders
def load_items(path: Path = MASTER_FILE) -> pd.DataFrame:
    df, sheet = _read(path, "Stok Barang", "items")
    rows = []
    for r in df.to_dict("records"):
        num, flag = parse_qty(r["stok"])
        kat = _text(r["kategori"])
        kat_norm = CATEGORY_ALIASES.get(kat.lower(), kat.title()) if kat else None
        rows.append({
            "kode": norm_code(r["kode"]), "nama": _text(r["nama"]), "kategori": kat_norm,
            "satuan": norm_unit(r["satuan"]), "satuan_asli": _text(r["satuan"]),
            "lokasi": _text(r["lokasi"]), "lokasi_key": loc_key(r["lokasi"]),
            "stok_raw": _text(r["stok"]), "stok_num": num, "stok_flag": flag,
            "min_stok": parse_qty(r["minimum"])[0], "catatan": _text(r["catatan"]),
            "name_key": name_key(r["nama"]), "sumber": f"{sheet}, baris {r['_baris']}",
        })
    return pd.DataFrame(rows)


def load_end_stock(path: Path = ENDSTOCK_FILE) -> pd.DataFrame:
    df, sheet = _read(path, None, "endstock")
    rows = []
    for r in df.to_dict("records"):
        num, flag = parse_qty(r["qty"])
        tgl, tflag = parse_date(r["update"])
        rows.append({
            "kode": norm_code(r["kode"]), "nama": _text(r["nama"]), "lokasi": _text(r["lokasi"]),
            "qty_raw": _text(r["qty"]), "qty_num": num, "qty_flag": flag,
            "update_raw": _text(r["update"]), "update_date": tgl.isoformat() if tgl else None,
            "update_flag": tflag, "pic": _text(r["pic"]),
            "sumber": f"{sheet}, baris {r['_baris']}",
        })
    return pd.DataFrame(rows)


def _load_movements(path: Path, sheet: str, kind: str) -> pd.DataFrame:
    rows = []
    df, actual = _read(path, sheet, kind)
    for r in df.to_dict("records"):
        status = r.get("status") if kind == "keluar" else None
        tgl, tflag = parse_date(r["tgl"])
        num, qflag = parse_qty(r["qty"])
        flags = [
            f"tanggal: {tflag}" if tflag else None,
            f"jumlah: {qflag}" if qflag else None,
            "tanpa kode barang" if _blank(r["kode"]) else None,
            "tanpa nomor bukti" if _blank(r["bukti"]) or str(r["bukti"]).strip() == "-" else None,
            "satuan kosong" if _blank(r["satuan"]) else None,
        ]
        if kind == "keluar" and status and "belum" in str(status).lower():
            flags.append(f"status: {status}")
        rows.append({
            "jenis": kind, "tgl_raw": _text(r["tgl"]), "tgl": tgl.isoformat() if tgl else None,
            "bukti": _text(r["bukti"]), "kode": norm_code(r["kode"]), "nama": _text(r["nama"]),
            "qty_raw": _text(r["qty"]), "qty_num": num, "satuan": norm_unit(r["satuan"]),
            "pihak": _text(r["pihak"]), "petugas": _text(r["petugas"]), "lokasi": _text(r.get("lokasi")),
            "status": _text(status), "catatan": _text(r["catatan"]), "name_key": name_key(r["nama"]),
            "dup": 0, "peringatan": _join(flags), "sumber": f"{actual}, baris {r['_baris']}",
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
    df, sheet = _read(path, "Catatan WA", "wa")
    rows = []
    for r in df.to_dict("records"):
        tgl, _ = parse_date(r["tgl"])
        rows.append({
            "tgl": tgl.isoformat() if tgl else None, "pengirim": _text(r["pengirim"]),
            "pesan": _text(r["pesan"]), "sumber": f"{sheet}, baris {r['_baris']}",
        })
    return pd.DataFrame(rows)


def data_signature() -> tuple:
    """Penanda perubahan berkas data (waktu ubah). Dipakai agar database dibangun ulang bila berkas diganti."""
    return tuple((p.name, p.stat().st_mtime_ns if p.exists() else None) for p in (MASTER_FILE, ENDSTOCK_FILE))


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
