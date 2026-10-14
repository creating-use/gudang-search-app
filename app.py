"""Antarmuka web: Pencarian Informasi Stok dan Transaksi Gudang (CV Gudang Sejahtera, kasus simulasi)."""
import pandas as pd
import streamlit as st

from data_processing import build_database
from search_service import search_items

st.set_page_config(page_title="Pencarian Informasi Gudang", page_icon="📦", layout="wide")


@st.cache_resource
def get_db():
    return build_database()


conn = get_db()

EXAMPLES = ["lampu LED 12W", "kabel roll", "lakban bening", "kardus", "BRG013", "BRG099", "stok menipis", "data perlu verifikasi"]


def show(df: pd.DataFrame):
    """Tampilkan tabel sebagai teks agar kolom campuran (angka dan '—') tidak memicu peringatan Arrow."""
    st.dataframe(df.astype(object).where(df.notna(), "").astype(str), hide_index=True)


def set_query(text: str):
    st.session_state["query"] = text


st.title("Pencarian Informasi Stok dan Transaksi Gudang")
st.caption("CV Gudang Sejahtera (kasus simulasi) · contoh aplikasi untuk Project AI Solution for Enterprise. "
           "Data fiktif dan tidak mewakili perusahaan nyata.")

with st.sidebar:
    st.header("Tentang aplikasi")
    st.write("Membantu menelusuri catatan barang dari beberapa sumber yang tidak seragam. "
             "Aplikasi menampilkan **kandidat, sumber, dan peringatan** — bukan satu angka stok yang dianggap pasti.")
    st.write("Aplikasi **tidak menggantikan pengecekan fisik stok**.")
    st.subheader("Sumber data")
    for table, label in [("items", "Master stok barang"), ("stock_end", "Catatan stok 31 Agustus"),
                         ("movements", "Transaksi masuk/keluar"), ("wa_notes", "Catatan WhatsApp")]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        st.write(f"- {label}: {n} baris")
    st.caption("Tanggal numerik dibaca sebagai hari/bulan/tahun. Tanggal tanpa tahun diasumsikan 2026 dan diberi penanda.")

query = st.text_input("Cari nama barang, kode (mis. BRG001), atau lokasi rak (mis. A1)", key="query",
                      placeholder="Contoh: lampu LED 12W")
for row in (EXAMPLES[:4], EXAMPLES[4:]):
    for col, ex in zip(st.columns(4), row):
        col.button(ex, on_click=set_query, args=(ex,), key=f"ex_{ex}")

if not query.strip():
    st.info("Masukkan nama atau kode barang, atau pilih salah satu contoh di atas.")
    st.stop()

result = search_items(conn, query)

if result.status == "not_found":
    st.error(result.message)
    if result.suggestions:
        st.write("Nama yang paling mendekati (hanya saran, bukan hasil pencarian): " + ", ".join(result.suggestions))
    st.stop()

if result.status == "listing":
    st.subheader(result.listing_title)
    st.warning(result.message)
    show(result.listing)
    st.stop()

st.success(result.message)
for c in result.candidates:
    with st.container(border=True):
        st.subheader(f"{c.kode or '(tanpa kode)'} — {c.nama}")
        st.caption(f"{c.kategori or '—'} · satuan {c.satuan or '—'} · lokasi {c.lokasi or '—'} · cocok karena: {c.reason}")

        if c.warnings:
            st.markdown("**Perlu verifikasi**")
            for w in c.warnings:
                st.warning(w, icon="⚠️")
        else:
            st.info("Tidak ada peringatan data untuk barang ini. Tetap verifikasi fisik bila angka akan dipakai untuk keputusan.")

        st.markdown("**Nilai stok per sumber**")
        show(pd.DataFrame(c.stock_values))

        if c.similar:
            st.markdown("**Barang dengan nama serupa (tidak digabung)**")
            show(pd.DataFrame(c.similar)[["kode", "nama", "lokasi", "stok", "alasan"]].rename(
                columns={"kode": "Kode", "nama": "Nama", "lokasi": "Lokasi", "stok": "Stok tercatat", "alasan": "Alasan"}))

        tab_tx, tab_wa = st.tabs([f"Transaksi ({len(c.transactions)})", f"Catatan WhatsApp ({len(c.wa_notes)})"])
        with tab_tx:
            s = c.summary
            m1, m2, m3 = st.columns(3)
            m1.metric("Total masuk (tercatat)", s["masuk"] if s["masuk"] is not None else "—")
            m2.metric("Total keluar (tercatat)", s["keluar"] if s["keluar"] is not None else "—")
            m3.metric("Baris tanpa angka jelas", s["tanpa_angka"])
            st.caption("Total hanya menjumlahkan baris bertanda kode dan bukan duplikat. Ini BUKAN stok akhir: saldo awal tidak ada pada data.")
            if not c.transactions.empty:
                view = c.transactions[["jenis", "tgl", "tgl_raw", "bukti", "kode", "qty_raw", "satuan", "pihak", "petugas", "peringatan", "sumber"]]
                show(view.rename(columns={
                    "jenis": "Jenis", "tgl": "Tanggal (terbaca)", "tgl_raw": "Tanggal (asli)", "bukti": "No. bukti",
                    "kode": "Kode", "qty_raw": "Jumlah (asli)", "satuan": "Satuan", "pihak": "Supplier / tujuan",
                    "petugas": "Petugas", "peringatan": "Peringatan", "sumber": "Rujukan"}))
        with tab_wa:
            if c.wa_notes:
                show(pd.DataFrame(c.wa_notes))
            else:
                st.write("Tidak ada catatan WhatsApp yang terkait.")
