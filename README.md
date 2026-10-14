# Pencarian Informasi Stok dan Transaksi Gudang

Contoh aplikasi untuk **CV Gudang Sejahtera (kasus simulasi)** pada Project "AI Solution for Enterprise".
Data fiktif. Aplikasi membantu menelusuri catatan barang dari beberapa sumber yang tidak seragam dan
menampilkan **kandidat, sumber, serta peringatan** — bukan satu angka stok yang dianggap pasti.

## Yang dilakukan aplikasi
- Mencari berdasarkan nama barang (toleran penulisan berbeda), kode (mis. `BRG013`), atau lokasi rak (mis. `A1`).
- Menampilkan nilai stok **per sumber** beserta rujukan sheet dan nomor baris.
- Menandai: angka stok berbeda antar sumber, nilai perkiraan / tidak diketahui / kosong, kode berbeda dengan nama
  serupa (**tidak digabung**), transaksi duplikat, transaksi tanpa kode, tanggal yang tidak jelas.
- Menjawab pertanyaan umum: "stok menipis", "data perlu verifikasi".
- Jika tidak ada data: menyatakan **tidak ditemukan**, tidak mengarang hasil.

Pendekatan: pencarian berbasis kata kunci dan aturan. Tidak memakai model AI generatif dan tidak memerlukan API key.

## Struktur
| Berkas | Fungsi |
|---|---|
| `app.py` | Antarmuka web (Streamlit) |
| `data_processing.py` | Membaca Excel, menormalisasi, membangun SQLite di memori |
| `search_service.py` | Logika pencarian, pencocokan, dan peringatan |
| `data/` | Dua berkas Excel simulasi |
| `tests/` | Uji logika dan uji asap antarmuka |
| `requirements.txt` | Daftar dependency |

## Menjalankan secara lokal
```
pip install -r requirements.txt
streamlit run app.py
```
Uji: `python tests/test_search.py` dan `python tests/test_app_smoke.py`.

## Mendapatkan URL publik (platform bebas pilihan)
Platform apa pun yang dapat menjalankan aplikasi Python dari repository bisa dipakai. Yang umumnya diminta platform:

| Isian | Nilai |
|---|---|
| Build / install command | `pip install -r requirements.txt` |
| Start command | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
| Entry file (jika platform meminta berkas utama) | `app.py` |
| Environment variable | Tidak ada yang wajib |

Catatan:
- Database SQLite **dibangun ulang dari Excel setiap aplikasi start**, sehingga tetap benar pada platform yang
  menghapus file lokal saat restart.
- Beberapa platform gratis menidurkan aplikasi saat sepi; buka URL beberapa menit sebelum demo.
- Batas memori dan fitur gratis tiap platform dapat berubah; cek dokumentasi platform sebelum memilih.
- Contoh ini **belum diuji di platform deploy mana pun**; hanya diuji lokal.

## Keterbatasan
- Total masuk/keluar bukan stok akhir karena saldo awal tidak ada pada data.
- Tanggal numerik dibaca hari/bulan/tahun; tanggal tanpa tahun diasumsikan 2026 dan diberi penanda.
- Pencocokan nama memakai aturan sederhana; alias yang sangat berbeda dapat terlewat.
- Aplikasi tidak menggantikan pengecekan fisik stok.
