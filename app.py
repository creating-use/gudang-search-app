"""Antarmuka web: Gudang Search - pencarian informasi stok dan transaksi gudang."""
import os
import re

import pandas as pd
import streamlit as st

from data_processing import DataFileError, build_database, data_signature
from llm_service import LLMService, load_config
from search_service import merge_by_names, search_items

st.set_page_config(page_title="Pencarian Informasi Gudang", page_icon="📦", layout="wide")


@st.cache_resource
def get_db(signature):
    """Dibangun ulang bila berkas data berubah (signature = waktu ubah berkas)."""
    return build_database()


def _secret(name, default=None):
    """Baca dari Streamlit secrets, lalu environment. Kunci API tidak pernah ditulis ke kode atau repo."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


@st.cache_resource
def get_llm():
    """Satu layanan AI dibagikan ke semua sesi agar batas pemakaian dihitung bersama."""
    return LLMService(load_config(_secret))


try:
    conn = get_db(data_signature())
except DataFileError as exc:
    st.error(f"Data tidak dapat dimuat: {exc}")
    st.caption("Periksa berkas di folder data/ (nama berkas, nama sheet, dan kolom wajib), lalu muat ulang halaman.")
    st.stop()

llm = get_llm()
st.session_state.setdefault("ai_calls", 0)
st.session_state.setdefault("ai_explain", {})
GUARD_REASONS = {"disabled", "no_key", "breaker", "cooldown", "session", "rpm", "tpm", "rpd", "interval", "query_length", "no_result"}
QUIET_REASONS = {"disabled", "no_key", "query_length", "no_result"}


def count_call(outcome):
    """Hitung panggilan ke sesi ini hanya bila benar-benar menghubungi API (bukan cache, bukan ditolak pagar)."""
    if (outcome.ok and not outcome.cached) or (not outcome.ok and outcome.reason not in GUARD_REASONS):
        st.session_state["ai_calls"] += 1

EXAMPLES = ["lampu LED 12W", "kabel roll", "lakban bening", "kardus", "BRG013", "BRG099", "stok menipis", "data perlu verifikasi"]


def show(df: pd.DataFrame):
    """Tampilkan tabel sebagai teks agar kolom campuran (angka dan '—') tidak memicu peringatan Arrow."""
    st.dataframe(df.astype(object).where(df.notna(), "").astype(str), hide_index=True)


def set_query(text: str):
    st.session_state["query"] = text


st.title("Pencarian Informasi Stok dan Transaksi Gudang")
st.caption("CV Gudang Sejahtera · Gudang Search v1.1 · Informasi stok dan transaksi dari berbagai sumber catatan gudang")

with st.sidebar:
    st.header("Tentang aplikasi")
    st.write("Membantu menelusuri catatan barang dari beberapa sumber yang tidak seragam. "
             "Aplikasi menampilkan **kandidat, sumber, dan peringatan** — bukan satu angka stok yang dianggap pasti.")
    st.write("Aplikasi **tidak menggantikan pengecekan fisik stok**.")
    st.write("Pencarian utama memakai aturan. **AI hanya dipakai sesekali** (memahami kata kunci saat tidak ada hasil, "
             "dan penjelasan lewat tombol) dengan batas pemakaian.")
    st.subheader("Sumber data")
    for table, label in [("items", "Master stok barang"), ("stock_end", "Catatan stok akhir"),
                         ("movements", "Transaksi masuk/keluar"), ("wa_notes", "Catatan WhatsApp")]:
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        st.write(f"- {label}: {n} baris")
    st.caption("Tanggal numerik dibaca sebagai hari/bulan/tahun. Tanggal tanpa tahun diasumsikan 2026 dan diberi penanda.")
    ai_slot = st.empty()   # diisi SETELAH pencarian berjalan agar hitungan pemakaian tidak telat satu langkah


def render_ai_status():
    """Status AI di sidebar; boleh dipanggil berulang (menimpa isi sebelumnya)."""
    with ai_slot.container():
        st.subheader("Fitur AI")
        snap = llm.snapshot(st.session_state["ai_calls"])
        if snap["reason"] in ("disabled", "no_key"):
            st.caption(snap["message"])
        else:
            st.write("Status: **aktif**" if (snap["allowed"] or snap["reason"] == "interval")   # jeda 3 detik bukan pembatasan
                     else f"Status: **dibatasi sementara** · {snap['message']}")
        if llm.cfg.debug:
            with st.expander("Diagnostik AI (LLM_DEBUG aktif)"):
                st.caption("Hanya untuk uji. Matikan LLM_DEBUG setelah selesai.")
                usage = {"permintaan_1_menit": f"{snap['rpm']}/{snap['rpm_limit']}", "token_1_menit": f"{snap['tokens_1m']}/{snap['tpm_limit']}",
                         "permintaan_24_jam": f"{snap['rpd']}/{snap['rpd_limit']}", "panggilan_sesi_ini": st.session_state["ai_calls"]}
                st.json({"model": llm.cfg.model, "pemakaian": usage, **(llm.last_debug or {"info": "belum ada panggilan"})})

query = st.text_input("Cari nama barang, kode (mis. BRG001), atau lokasi rak (mis. A1)", key="query",
                      placeholder="Contoh: lampu LED 12W")
for row in (EXAMPLES[:4], EXAMPLES[4:]):
    for col, ex in zip(st.columns(4), row):
        col.button(ex, on_click=set_query, args=(ex,), key=f"ex_{ex}")

if not query.strip():
    render_ai_status()
    st.info("Masukkan nama atau kode barang, atau pilih salah satu contoh di atas.")
    st.stop()

result = search_items(conn, query)

# (a) Pemahaman kata kunci oleh AI: hanya bila aturan tidak menemukan apa pun dan bukan pencarian kode.
ai_notice = None
if result.status == "not_found" and not re.search(r"brg\s*-?\s*\d", query.lower()):
    vocab = [r[0] for r in conn.execute("SELECT nama FROM items WHERE nama IS NOT NULL")]
    out = llm.rewrite(query, vocab, st.session_state["ai_calls"])
    count_call(out)
    if out.ok and out.value:
        merged = merge_by_names(conn, query, out.value)
        if merged:
            result = merged
    elif out.reason == "no_match":
        ai_notice = out.message              # AI dipanggil tetapi tidak ada padanan: tetap diberi tahu
    elif not out.ok and out.reason not in QUIET_REASONS:
        ai_notice = out.message or "Fitur AI sedang dibatasi; memakai pencarian biasa."

render_ai_status()
if result.status == "not_found":
    if ai_notice:
        st.caption(ai_notice)
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

# (b) Penjelasan AI lewat tombol (disembunyikan bila pemakaian mendekati batas).
qkey = " ".join(query.lower().split())
snap = llm.available("explain", st.session_state["ai_calls"])
if snap.allowed or snap.reason == "interval":   # jeda antarpanggilan hanya sebentar: tombol tetap tampil
    if st.button("Jelaskan dengan AI", key="btn_explain", help="Ringkasan dari hasil di bawah. Memakai kuota AI yang terbatas."):
        out = llm.explain(result, st.session_state["ai_calls"])
        count_call(out)
        if out.reason == "interval":
            st.warning(out.message)               # sementara, tidak disimpan
        else:
            st.session_state["ai_explain"][qkey] = out
elif snap.reason not in QUIET_REASONS and qkey not in st.session_state["ai_explain"]:
    st.caption(f"Tombol penjelasan AI disembunyikan sementara untuk menjaga kuota. {snap.message}")
render_ai_status()
shown = st.session_state["ai_explain"].get(qkey)
if shown is not None:
    if shown.ok:
        st.info("**Penjelasan AI** (disusun dari hasil di bawah, bukan data sumber; periksa rujukan sebelum dipakai)\n\n" + str(shown.value))
    else:
        st.warning(shown.message or "Penjelasan AI tidak tersedia.")

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
