"""Uji tampilan fitur AI dengan transport tiruan (tanpa API sungguhan). Jalankan: python tests/test_app_ai.py"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import streamlit as st
from streamlit.testing.v1 import AppTest
import llm_service

CALLS = []


def fake_transport(url, headers, body, timeout):
    CALLS.append(body)
    if "systemInstruction" in body and "JSON" in body["systemInstruction"]["parts"][0]["text"]:
        text = '{"nama": ["Lampu LED 12 watt", "Lampu LED 12W"]}'
    else:
        text = "BRG002 dan BRG017 sama-sama tercatat 36; kemungkinan salinan data, verifikasi fisik."
    return {"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"totalTokenCount": 400}}


def failing_transport(url, headers, body, timeout):
    raise llm_service.LLMError("rate_limit", 60)


def fresh(env, transport):
    for k in ("GEMINI_API_KEY", "LLM_RPM_HIDE_AT", "LLM_ENABLED", "LLM_DEBUG"):
        os.environ.pop(k, None)
    os.environ.update(env)
    llm_service.default_transport = transport
    st.cache_resource.clear()
    CALLS.clear()
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)
    at.run(); assert not at.exception, at.exception
    return at


def search(at, q):
    at.text_input(key="query").set_value(q).run(); assert not at.exception, at.exception
    return at


def texts(at):
    return " ".join(x.value for g in (at.markdown, at.success, at.info, at.caption) for x in g)


def test_tanpa_kunci_aplikasi_tetap_jalan_dan_tidak_ada_tombol():
    at = search(fresh({}, fake_transport), "lampu LED 12W")
    assert len(at.success) == 1 and not [b for b in at.button if b.label == "Jelaskan dengan AI"] and not CALLS
    search(at, "bohlam")
    assert len(at.error) == 1 and not CALLS            # tetap 'tidak ditemukan', tanpa memanggil AI


def test_bohlam_dipahami_ai_lalu_tombol_penjelasan():
    at = search(fresh({"GEMINI_API_KEY": "k"}, fake_transport), "bohlam")
    assert "dipahami AI" in texts(at) and len(CALLS) == 1 and not at.error
    btn = [b for b in at.button if b.label == "Jelaskan dengan AI"]; assert btn   # tombol tetap tampil walau baru ada panggilan
    btn[0].click().run(); assert not at.exception
    assert "Mohon tunggu" in " ".join(w.value for w in at.warning) and len(CALLS) == 1   # klik terlalu cepat: ditahan, tanpa panggilan
    import time; time.sleep(3.2)
    [b for b in at.button if b.label == "Jelaskan dengan AI"][0].click().run()
    assert "Penjelasan AI" in texts(at) and len(CALLS) == 2
    search(at, "bohlam"); assert len(CALLS) == 2       # rerun memakai cache, tidak menambah panggilan


def test_pencarian_biasa_tidak_memanggil_ai():
    at = search(fresh({"GEMINI_API_KEY": "k"}, fake_transport), "lampu LED 12W")
    assert not CALLS
    search(at, "BRG099"); assert not CALLS             # pencarian kode tidak diterjemahkan AI
    search(at, "stok menipis"); assert not CALLS


def test_tombol_hilang_saat_batas_tercapai():
    at = search(fresh({"GEMINI_API_KEY": "k", "LLM_RPM_HIDE_AT": "1"}, fake_transport), "lampu LED 12W")
    btn = [b for b in at.button if b.label == "Jelaskan dengan AI"]; assert btn
    btn[0].click().run(); assert len(CALLS) == 1
    search(at, "kardus")
    assert not [b for b in at.button if b.label == "Jelaskan dengan AI"]           # 1/1 per menit -> disembunyikan
    assert "disembunyikan sementara" in " ".join(c.value for c in at.caption)


def test_api_gagal_tidak_memunculkan_error_mentah():
    at = search(fresh({"GEMINI_API_KEY": "k"}, failing_transport), "bohlam")
    assert not at.exception and len(at.error) == 1      # tetap 'tidak ditemukan' biasa
    assert "tidak tersedia" in " ".join(c.value for c in at.caption)
    at2 = search(fresh({"GEMINI_API_KEY": "k"}, failing_transport), "lampu LED 12W")
    [b for b in at2.button if b.label == "Jelaskan dengan AI"][0].click().run()
    assert not at2.exception and "tidak tersedia" in " ".join(w.value for w in at2.warning)


def side(at):
    return " ".join(x.value for g in (at.sidebar.markdown, at.sidebar.caption) for x in g)


def empty_transport(url, headers, body, timeout):
    CALLS.append(body)
    return {"candidates": [{"content": {"parts": [{"text": '{"nama": []}'}]}}], "usageMetadata": {"totalTokenCount": 300}}


def test_ai_dipanggil_tapi_tidak_ada_padanan_tetap_diberi_tahu():
    at = search(fresh({"GEMINI_API_KEY": "k"}, empty_transport), "sepeda motor")
    assert len(CALLS) == 1 and len(at.error) == 1
    assert "tidak menemukan nama barang yang cocok" in " ".join(c.value for c in at.caption)


def test_angka_pemakaian_tidak_tampil_di_sidebar_kecuali_debug():
    at = search(fresh({"GEMINI_API_KEY": "k"}, fake_transport), "bohlam")
    assert len(CALLS) == 1 and "Status: **aktif**" in side(at)
    assert "permintaan per menit" not in side(at) and "/250" not in side(at) and not list(at.sidebar.json)
    at2 = search(fresh({"GEMINI_API_KEY": "k", "LLM_DEBUG": "true"}, fake_transport), "bohlam")
    usage = at2.sidebar.json[0].value
    assert '"permintaan_1_menit": "1/15"' in usage.replace("':", '":').replace("'", '"') or "1/15" in usage   # hitungan tidak telat


def test_panel_diagnostik_hanya_bila_debug_aktif():
    at = search(fresh({"GEMINI_API_KEY": "k", "LLM_DEBUG": "true"}, fake_transport), "bohlam")
    assert "Diagnostik AI" in " ".join(e.label for e in at.sidebar.expander)
    at2 = search(fresh({"GEMINI_API_KEY": "k"}, fake_transport), "bohlam")
    assert not list(at2.sidebar.expander)

def test_keterangan_ai_tetap_tampil_saat_pencarian_diulang():
    at = search(fresh({"GEMINI_API_KEY": "k"}, empty_transport), "sepeda motor")
    at.run()
    caps = [c.value for c in at.caption if "AI sudah dimintai bantuan" in c.value]
    assert caps and len(CALLS) == 1, (caps, len(CALLS))



if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try: fn(); print("PASS", name)
            except Exception as e: fails += 1; print("FAIL", name, type(e).__name__, e)
    sys.exit(1 if fails else 0)
