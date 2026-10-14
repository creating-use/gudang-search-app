"""Uji sederhana. Jalankan dari folder proyek:  python -m pytest -q   atau   python tests/test_search.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_processing import build_database, parse_date, parse_qty  # noqa: E402
from search_service import search_items  # noqa: E402

CONN = build_database()


def warnings_text(result):
    return " | ".join(w for c in result.candidates for w in c.warnings)


def test_parse_qty():
    assert parse_qty(24) == (24, None)
    assert parse_qty("36 pcs") == (36, "angka ditulis bersama teks")
    assert parse_qty("sekitar 120") == (120, "perkiraan")
    assert parse_qty("?") == (None, "tidak diketahui")
    assert parse_qty(None) == (None, "kosong")


def test_parse_date():
    assert parse_date("4 Agu 2026")[0].isoformat() == "2026-08-04"
    assert parse_date("05/08/26")[0].isoformat() == "2026-08-05"
    assert parse_date("2026/08/03")[0].isoformat() == "2026-08-03"
    assert parse_date("29 Agu")[1] == "tahun diasumsikan 2026"
    assert parse_date("minggu lalu") == (None, "tanggal tidak dapat dibaca")


def test_tc01_nama_konsisten_menampilkan_sumber():
    r = search_items(CONN, "obeng set")
    assert r.status == "ok" and r.candidates[0].kode == "BRG009"
    assert r.candidates[0].stock_values[0]["Rujukan"].startswith("Stok Barang")


def test_tc02_kode_tidak_ditemukan():
    r = search_items(CONN, "BRG099")
    assert r.status == "not_found" and "tidak ditemukan" in r.message and not r.candidates


def test_tc02b_nama_tidak_ada():
    r = search_items(CONN, "sepeda motor")
    assert r.status == "not_found" and not r.candidates


def test_tc03_nama_serupa_tidak_digabung():
    r = search_items(CONN, "kabel roll")
    kodes = {c.kode for c in r.candidates}
    assert {"BRG001", "BRG016"} <= kodes  # dua kode tetap terpisah
    assert "kemungkinan barang yang sama" in warnings_text(r).lower()


def test_tc04_konflik_stok_ditandai():
    r = search_items(CONN, "lakban bening")
    text = warnings_text(r)
    assert "angka stok berbeda" in text.lower()
    assert "64" in text and "58" in text


def test_tc05_data_kosong_tidak_ditafsirkan():
    r = search_items(CONN, "BRG016")
    c = r.candidates[0]
    assert c.stock_values[0]["Angka terbaca"] == "—"
    assert "kosong atau tidak jelas" in " ".join(c.warnings)


def test_perkiraan_dan_tidak_diketahui():
    assert "perkiraan" in warnings_text(search_items(CONN, "BRG013"))
    assert "tidak diketahui" in warnings_text(search_items(CONN, "BRG017"))


def test_duplikat_po_tidak_dihitung():
    c = search_items(CONN, "tang kombinasi").candidates[0]
    assert c.summary["dup_masuk"] == 1
    assert c.summary["masuk"] == 8 + 5  # PO-2412 + PO-2429 (baris kedua tidak dihitung)


def test_transaksi_tanpa_kode_diberi_peringatan():
    r = search_items(CONN, "kardus")
    assert any(c.summary["tanpa_kode"] == 1 for c in r.candidates)
    assert "tanpa kode" in warnings_text(r)


def test_wa_terkait():
    c = search_items(CONN, "BRG017").candidates[0]
    assert any("BRG017" in n["Pesan"] for n in c.wa_notes)


def test_listing_menipis_dan_bermasalah():
    assert search_items(CONN, "stok menipis").status == "listing"
    r = search_items(CONN, "data perlu verifikasi")
    assert r.status == "listing" and len(r.listing) > 0


def test_query_kosong():
    assert search_items(CONN, "  ").status == "empty"


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
