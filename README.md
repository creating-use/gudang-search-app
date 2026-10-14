# Gudang Search

Aplikasi web untuk menelusuri **informasi stok dan transaksi barang gudang** dari beberapa sumber catatan yang tidak seragam.
Hasil pencarian menampilkan **kandidat barang, nilai per sumber beserta rujukannya, dan peringatan** bila data berbeda atau
tidak lengkap, bukan satu angka stok yang dianggap pasti. Aplikasi bersifat hanya-baca dan tidak menggantikan pengecekan fisik stok.

## Cara menggunakan

1. **Buka aplikasi** melalui browser. Tidak ada login.
2. **Ketik pencarian** pada kolom di bagian atas, lalu tekan Enter. Anda dapat mencari dengan:
   - nama barang, mis. `lampu LED 12W` (penulisan yang sedikit berbeda tetap dikenali),
   - kode barang, mis. `BRG013`,
   - lokasi rak, mis. `A1`,
   - atau memilih salah satu tombol contoh di bawah kolom pencarian.
3. **Baca hasilnya.** Setiap kandidat menampilkan:

   | Bagian | Artinya |
   |---|---|
   | Perlu verifikasi | Peringatan data: angka stok berbeda antar sumber, nilai perkiraan atau kosong, kode berbeda dengan nama serupa, transaksi ganda, dan sejenisnya |
   | Nilai stok per sumber | Angka dari tiap sumber, lengkap dengan rujukan (nama sheet dan nomor baris) agar dapat dicek ulang |
   | Barang dengan nama serupa | Barang lain yang mungkin sama; **tidak digabung** otomatis |
   | Transaksi | Catatan barang masuk dan keluar. Total masuk/keluar bukan stok akhir karena saldo awal tidak tersedia |
   | Catatan WhatsApp | Pesan yang menyebut barang tersebut |

4. **Pertanyaan umum.** Ketik `stok menipis` untuk melihat barang di bawah stok minimum atau yang stoknya tidak jelas, atau
   `data perlu verifikasi` untuk daftar barang yang memiliki peringatan data.
5. **Jika data tidak ada**, aplikasi menyatakan tidak ditemukan dan tidak mengarang hasil. Itu tidak berarti barangnya tidak
   ada secara fisik: periksa ejaan, coba kata kunci lain, atau cek catatan sumber.

## Fitur AI (opsional)

Pencarian utama berbasis aturan dan selalu berjalan lebih dulu. Fitur AI hanya aktif bila kunci API dikonfigurasi; tanpa itu
aplikasi tetap berfungsi penuh. AI dipakai pada dua keadaan:

- **Memahami kata kunci.** Bila aturan tidak menemukan hasil, AI memetakan kata kunci ke nama barang yang ada pada data
  (misalnya "bohlam" ke "lampu"). Hasilnya tetap dicari dari data; nama di luar data diabaikan.
- **Penjelasan hasil.** Tombol **Jelaskan dengan AI** menyusun ringkasan dari hasil yang sudah ditemukan, dengan rujukan
  sheet dan baris. Jawaban yang memuat angka yang tidak ada pada data ditolak. Penjelasan AI bukan data sumber: selalu periksa rujukannya.

Bila AI tidak dapat dipanggil (kuota, jaringan, kunci tidak diatur, atau jawaban tidak lolos validasi), aplikasi kembali ke
hasil berbasis aturan dan menampilkan pesan singkat.

### Mengatur AI

Simpan kunci di pengaturan *secrets* platform atau di `.streamlit/secrets.toml` (sudah masuk `.gitignore`); **jangan** menaruhnya
di kode atau repository. Contoh ada pada `.streamlit/secrets.toml.example`:

```
GEMINI_API_KEY = "isi-kunci-api-anda"
GEMINI_MODEL = "isi-model-id-yang-tersedia-di-akun-anda"
```

### Rekomendasi pengaturan batas pemakaian

Sesuaikan dengan kuota akun Anda. Nilai bawaan ada di `llm_service.py` dan dapat diubah lewat secrets.

- Sembunyikan tombol AI **jauh sebelum** batas permintaan per menit dan per hari tercapai, dan sisakan cadangan untuk penjelasan lewat tombol.
- Batasi jumlah panggilan per sesi pengguna dan beri jeda minimal antarpanggilan.
- Simpan jawaban untuk pertanyaan yang sama agar tidak memakai kuota lagi.
- Jeda otomatis setelah error batas penggunaan dari penyedia API, dan setelah beberapa kegagalan beruntun.
- Batasi panjang kata kunci, jumlah data yang dikirim, dan panjang jawaban.
- Sediakan saklar mati (`LLM_ENABLED = "false"`) untuk mematikan AI tanpa mengubah kode.
- Hitungan pemakaian pada aplikasi bersifat perkiraan (disimpan di memori dan kembali nol saat aplikasi restart), jadi sisakan margin dari batas sebenarnya.
- Gunakan `LLM_DEBUG = "true"` hanya sementara saat menguji: panel diagnostiknya terlihat semua pengunjung.

## Memperbarui data

Data dibaca dari dua berkas Excel di folder `data/`. Untuk memperbarui, **ganti isi berkas dengan nama yang sama**, lalu
commit ke repository (atau jalankan ulang aplikasi bila dipakai lokal).

- `Berkas_Gudang_Dari_Perusahaan.xlsx` harus memiliki sheet `Stok Barang`, `Barang Masuk`, `Barang Keluar`, dan `Catatan WA`
  (huruf besar/kecil bebas).
- `Catatan_Stok_Akhir.xlsx`: sheet pertama yang dibaca, namanya bebas.
- Kolom dikenali dari **nama header**, bukan urutan. Kolom dan baris baru boleh ditambahkan; baris kosong dilewati.
- Kolom wajib: Stok Barang (kode, nama, stok), Barang Masuk/Keluar (tanggal, kode, jumlah), Catatan WA (tanggal, pesan), Stok Akhir (kode, qty).
  Jika sheet atau kolom wajib hilang, aplikasi menampilkan pesan yang menyebut apa yang kurang.

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

Catatan: basis data SQLite dibangun ulang dari Excel setiap aplikasi mulai, jadi tidak bergantung pada file lokal yang permanen.
Beberapa platform gratis menidurkan aplikasi saat sepi; buka aplikasi beberapa menit sebelum dipakai. Batas fitur gratis tiap
platform dapat berubah, jadi periksa dokumentasi platform.

## Struktur proyek

| Berkas | Fungsi |
|---|---|
| `app.py` | Antarmuka web (Streamlit) |
| `data_processing.py` | Membaca Excel, menormalisasi, membangun SQLite di memori |
| `search_service.py` | Logika pencarian, pencocokan, dan peringatan (berbasis aturan) |
| `llm_service.py` | Lapisan AI opsional: klien API, pagar pemakaian, validasi keluaran |
| `data/` | Berkas data Excel |
| `tests/` | Uji logika, uji AI (tanpa memanggil API sungguhan), dan uji asap antarmuka |
| `requirements.txt` | Daftar dependency |

Menjalankan uji: `python tests/test_search.py`, `python tests/test_llm.py`, `python tests/test_app_ai.py`, `python tests/test_app_smoke.py`.

## Keterbatasan

- Total masuk/keluar bukan stok akhir karena saldo awal tidak ada pada data.
- Tanggal numerik dibaca hari/bulan/tahun; tanggal tanpa tahun diasumsikan 2026 dan diberi penanda (`DEFAULT_YEAR` di `data_processing.py`).
- Pencocokan nama memakai aturan; padanan yang sangat berbeda dari data hanya dibantu AI bila fitur AI aktif dan kuota tersedia.
- Keluaran AI dapat berbeda dari satu panggilan ke panggilan lain dan tidak boleh dianggap sebagai data sumber.
- Aplikasi hanya membaca berkas di folder `data/` dan tidak terhubung ke sistem inventori.

## Catatan data

Repository ini menyertakan **data contoh untuk keperluan demonstrasi**. Jangan mengunggah data perusahaan yang bersifat rahasia
ke repository publik.
