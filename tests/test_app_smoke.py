"""Uji asap UI: aplikasi dapat dirender tanpa error. Jalankan: python tests/test_app_smoke.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from streamlit.testing.v1 import AppTest

def run(query):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    if query:
        at.text_input(key="query").set_value(query).run()
        assert not at.exception, (query, at.exception)
    return at

if __name__ == "__main__":
    for q in ["", "lampu LED 12W", "BRG099", "stok menipis", "data perlu verifikasi", "kardus"]:
        at = run(q)
        print("OK", repr(q), "| warnings:", len(at.warning), "| errors:", len(at.error), "| dataframes:", len(at.dataframe))
