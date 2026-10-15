# Gudang Search

Aplikasi web untuk menelusuri **informasi stok dan transaksi barang gudang** dari beberapa sumber catatan yang tidak seragam.
Hasil pencarian menampilkan **kandidat barang, nilai per sumber beserta rujukannya, dan peringatan** bila data berbeda atau
tidak lengkap, bukan satu angka stok yang dianggap pasti. Aplikasi bersifat hanya-baca dan tidak menggantikan pengecekan fisik stok.

## Cara menggunakan

1. **Buka aplikasi** melalui browser. Tidak ada login.
2. **Ketik pencarian** pada kolom di bagian atas, lalu tekan Enter. Anda dapat mencari dengan nama barang
   (mis. `lampu LED 12W`), kode barang (mis. `BRG013`), atau lokasi rak (mis. `A1`). Tombol contoh di bawah kolom juga bisa dipakai.
3. **Baca hasilnya.** Setiap kandidat menampilkan peringatan **Perlu verifikasi**, nilai stok per sumber beserta rujukan
   (nama sheet dan nomor baris), barang bernama serupa (tidak digabung otomatis), transaksi masuk dan keluar, serta catatan WhatsApp
   yang menyebut barang tersebut. Total masuk/keluar bukan stok akhir karena saldo awal tidak tersedia.
4. **Pertanyaan umum.** Ketik `stok menipis` untuk barang di bawah stok minimum atau yang stoknya tidak jelas, atau
   `data perlu verifikasi` untuk barang yang memiliki peringatan data.
5. **Jika data tidak ada**, aplikasi menyatakan tidak ditemukan dan tidak mengarang hasil. Periksa ejaan atau coba kata kunci lain.

## Fitur AI (opsional)

Pencarian utama berbasis aturan dan selalu berjalan lebih dulu. Fitur AI hanya aktif bila kunci API diatur; tanpa itu aplikasi
tetap berfungsi penuh. AI dipakai untuk dua hal:

- **Memahami kata kunci.** Bila aturan tidak menemukan hasil, AI memetakan kata kunci ke nama barang yang ada pada data
  (mis. "bohlam" ke "lampu"). Hasilnya tetap dicari dari data.
- **Penjelasan hasil.** Tombol **Jelaskan dengan AI** meringkas hasil yang sudah ditemukan. Jawaban yang memuat angka di luar
  data ditolak. Penjelasan AI bukan data sumber, jadi tetap periksa rujukannya.

Bila AI tidak dapat dipanggil (kuota, jaringan, kunci belum diatur, atau jawaban tidak valid), aplikasi kembali ke hasil
berbasis aturan dan menampilkan pesan singkat.

### Mengatur AI

Simpan kunci di pengaturan *secrets* platform atau di `.streamlit/secrets.toml` (sudah masuk `.gitignore`). **Jangan** menaruhnya
di kode atau repository. Contoh ada pada `.streamlit/secrets.toml.example`:

```
GEMINI_API_KEY = "isi-kunci-api-anda"
GEMINI_MODEL = "isi-model-id-yang-tersedia-di-akun-anda"
```

### Pengaturan batas pemakaian

Sesuaikan dengan kuota akun Anda; nilai bawaan ada di `llm_service.py` dan dapat diubah lewat secrets.

- Sembunyikan tombol AI jauh sebelum batas per menit dan per hari tercapai.
- Batasi panggilan per sesi, beri jeda antarpanggilan, dan simpan jawaban yang sama agar tidak memakai kuota lagi.
- Beri jeda otomatis setelah error batas dari penyedia API dan setelah beberapa kegagalan beruntun.
- Batasi panjang kata kunci, jumlah data yang dikirim, dan panjang jawaban.
- Sediakan saklar mati (`LLM_ENABLED = "false"`) untuk mematikan AI tanpa mengubah kode.
- Hitungan pemakaian bersifat perkiraan dan kembali nol saat aplikasi restart, jadi sisakan margin.
- Nyalakan `LLM_DEBUG = "true"` hanya sementara saat menguji; panelnya terlihat semua pengunjung.

## Menjalankan di komputer sendiri

```
pip install -r requirements.txt
streamlit run app.py
```

## Men-deploy

Platform apa pun yang dapat menjalankan aplikasi Python dari repository bisa dipakai.

| Isian | Nilai |
|---|---|
| Build / install command | `pip install -r requirements.txt` |
| Start command | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
| Entry file (jika diminta) | `app.py` |
| Secrets | Opsional; hanya untuk fitur AI |

Basis data SQLite dibangun ulang dari Excel setiap aplikasi mulai, jadi tidak bergantung pada file lokal yang permanen.
Platform gratis dapat menidurkan aplikasi saat sepi; buka aplikasi beberapa menit sebelum dipakai.

## Struktur proyek

| Berkas | Fungsi |
|---|---|
| `app.py` | Antarmuka web (Streamlit) |
| `data_processing.py` | Membaca Excel, menormalisasi, membangun SQLite di memori |
| `search_service.py` | Logika pencarian, pencocokan, dan peringatan (berbasis aturan) |
| `llm_service.py` | Lapisan AI opsional: klien API, pembatas pemakaian, validasi keluaran |
| `data/` | Berkas data Excel |
| `tests/` | Uji logika, uji AI (tanpa memanggil layanan AI sungguhan), dan uji tampilan |
| `requirements.txt` | Daftar dependency |

## Keterbatasan

- Total masuk/keluar bukan stok akhir karena saldo awal tidak ada pada data.
- Tanggal numerik dibaca hari/bulan/tahun; tanggal tanpa tahun diasumsikan 2026 dan diberi penanda.
- Padanan nama yang sangat berbeda dari data hanya dibantu AI bila fitur AI aktif dan kuota tersedia.
- Keluaran AI dapat berbeda antarpanggilan dan tidak boleh dianggap data sumber.
- Aplikasi hanya membaca berkas di folder `data/` dan tidak terhubung ke sistem inventori.

## Catatan data

Repository ini menyertakan **data contoh untuk keperluan demonstrasi**. Jangan mengunggah data perusahaan yang bersifat rahasia
ke repository publik.
