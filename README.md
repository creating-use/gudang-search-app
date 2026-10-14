# Pencarian Informasi Stok dan Transaksi Gudang

Aplikasi **Gudang Search** untuk **CV Gudang Sejahtera (kasus simulasi)**.
Data fiktif. Aplikasi membantu menelusuri catatan barang dari beberapa sumber yang tidak seragam dan
menampilkan **kandidat, sumber, serta peringatan** — bukan satu angka stok yang dianggap pasti.

## Yang dilakukan aplikasi
- Mencari berdasarkan nama barang (toleran penulisan berbeda), kode (mis. `BRG013`), atau lokasi rak (mis. `A1`).
- Menampilkan nilai stok **per sumber** beserta rujukan sheet dan nomor baris.
- Menandai: angka stok berbeda antar sumber, nilai perkiraan / tidak diketahui / kosong, kode berbeda dengan nama
  serupa (**tidak digabung**), transaksi duplikat, transaksi tanpa kode, tanggal yang tidak jelas.
- Menjawab pertanyaan umum: "stok menipis", "data perlu verifikasi".
- Jika tidak ada data: menyatakan **tidak ditemukan**, tidak mengarang hasil.

Pendekatan: **pencarian berbasis aturan selalu berjalan lebih dulu**. AI (Gemini lewat Google AI Studio) bersifat **opsional dan dibatasi**:
aplikasi tetap berfungsi penuh tanpa API key.

## Fitur AI (opsional, dibatasi)
| Kapan AI dipakai | Apa yang dilakukan | Pengaman |
|---|---|---|
| Aturan **tidak menemukan apa pun** (bukan pencarian kode) | Memetakan kata kunci ke **nama barang yang ada pada data** (mis. "bohlam" -> "Lampu LED 12 watt") | Nama di luar data dibuang; hasil tetap dicari ulang dari data |
| Pengguna menekan **"Jelaskan dengan AI"** | Menjelaskan hasil yang sudah ditemukan, dengan rujukan sheet/baris (pola RAG: retrieval berbasis aturan -> penjelasan oleh LLM) | Angka pada jawaban harus ada pada data yang dikirim, kalau tidak jawaban ditolak |

Batas pemakaian (default, sesuai free tier Gemini 3.5 Flash Lite pada akun pemilik: 15 RPM, 250K TPM, 500 RPD):
| Aturan | Nilai default |
|---|---|
| Tombol AI disembunyikan bila permintaan per 60 detik | >= 8 (dari 15) |
| Disembunyikan bila token per 60 detik | >= 60% dari 250K |
| Disembunyikan bila permintaan per 24 jam | >= 80% dari 500 |
| Pemahaman kata kunci otomatis berhenti lebih awal | 2 permintaan lebih rendah dari batas tombol (cadangan untuk tombol) |
| Maksimal panggilan per sesi pengguna | 8 |
| Jeda minimal antarpanggilan | 3 detik |
| Setelah error 429 dari API | AI dijeda minimal 90 detik |
| 3 kegagalan beruntun | AI dijeda 5 menit (circuit breaker) |
| Kata kunci | 3 sampai 120 karakter; jawaban yang sama disimpan 1 jam (tidak memakai kuota) |
| Panjang jawaban | maksimal 600 token keluaran |

Bila AI tidak bisa dipanggil (kuota, jaringan, kunci kosong, jawaban ditolak validasi), aplikasi **kembali ke hasil berbasis
aturan** dan menampilkan pesan singkat, tanpa error mentah. Penghitung pemakaian ada di memori server dan kembali nol saat
aplikasi restart; pemakaian kunci yang sama di tempat lain tidak terhitung. Karena itu batas dibuat jauh di bawah limit asli.

### Mengatur kunci API
Jangan menaruh kunci di kode atau repo (repo ini publik). Di Streamlit Community Cloud: *App settings -> Secrets*, isi:
```
GEMINI_API_KEY = "kunci-dari-google-ai-studio"
GEMINI_MODEL = "gemini-3.5-flash-lite"   # samakan persis dengan model ID di AI Studio
```
Secara lokal: salin `.streamlit/secrets.toml.example` menjadi `.streamlit/secrets.toml` (sudah di `.gitignore`).
Pengaturan opsional: `LLM_ENABLED = "false"` (matikan AI), `LLM_RPM_HIDE_AT`, `LLM_SESSION_MAX_CALLS`, `GEMINI_MAX_OUTPUT_TOKENS`.

## Struktur
| Berkas | Fungsi |
|---|---|
| `app.py` | Antarmuka web (Streamlit) |
| `data_processing.py` | Membaca Excel, menormalisasi, membangun SQLite di memori |
| `search_service.py` | Logika pencarian, pencocokan, dan peringatan (berbasis aturan) |
| `llm_service.py` | Lapisan AI opsional: klien Gemini, pagar pemakaian, validasi keluaran |
| `data/` | Dua berkas Excel simulasi (`Berkas_Gudang_Dari_Perusahaan.xlsx`, `Catatan_Stok_Akhir.xlsx`) |
| `tests/` | Uji logika dan uji asap antarmuka |
| `requirements.txt` | Daftar dependency |

## Menjalankan secara lokal
```
pip install -r requirements.txt
streamlit run app.py
```
Uji (tanpa memanggil API sungguhan): `python tests/test_search.py`, `python tests/test_llm.py`, `python tests/test_app_ai.py`, `python tests/test_app_smoke.py`.

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
- Aplikasi sudah di-deploy di Streamlit Community Cloud (Python 3.14); uji otomatis dijalankan lokal.

## Memperbarui data (Excel)
Data dibaca dari dua berkas di folder `data/`. Untuk memperbarui, **ganti isi berkas dengan nama yang sama** lalu commit ke repository
(Streamlit Community Cloud men-deploy ulang saat ada perubahan; periksa di dasbor platform bila belum). Aturannya:
- `Berkas_Gudang_Dari_Perusahaan.xlsx` harus memiliki sheet `Stok Barang`, `Barang Masuk`, `Barang Keluar`, `Catatan WA` (huruf besar/kecil bebas).
- `Catatan_Stok_Akhir.xlsx`: sheet pertama dibaca, namanya bebas (mis. "Agustus 2026", "September 2026").
- Kolom dikenali dari **nama header**, bukan urutan. Kolom baru boleh ditambah; baris baru boleh ditambah; baris kosong dilewati.
- Kolom wajib: Stok Barang (kode, nama, stok), Barang Masuk/Keluar (tanggal, kode, jumlah), Catatan WA (tanggal, pesan), Stok Akhir (kode, qty).
  Jika sheet atau kolom wajib hilang, aplikasi menampilkan pesan yang menyebut apa yang kurang, bukan error mentah.
- Jangan menaruh data perusahaan nyata pada repository publik.

## Keterbatasan
- Total masuk/keluar bukan stok akhir karena saldo awal tidak ada pada data.
- Tanggal numerik dibaca hari/bulan/tahun; tanggal tanpa tahun diasumsikan 2026 dan diberi penanda.
- Pencocokan nama memakai aturan; alias yang sangat berbeda hanya dibantu AI bila fitur AI aktif dan kuota tersedia.
- Tanggal tanpa tahun diasumsikan 2026 (`DEFAULT_YEAR` di `data_processing.py`); ubah bila data periode lain dipakai.
- Aplikasi tidak menggantikan pengecekan fisik stok.
