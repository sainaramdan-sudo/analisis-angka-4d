# Analisis Angka 4D

Aplikasi HTML statis untuk analisis statistik historis angka empat digit dan backtesting baseline sederhana. Tidak menjamin prediksi atau kemenangan.

## Menjalankan
Buka `index.html` langsung di browser. Untuk Vercel, import repository, pilih Framework Preset **Other**, biarkan build command kosong. Tidak perlu API key atau environment variables.

Data input disimpan hanya di localStorage browser bila tombol Simpan lokal ditekan.


## Monitor arsip dan kandidat statistik
- Monitor membaca `data/hk4d.json`, yang diperbarui oleh workflow GitHub Actions jika sumber dapat dibaca.
- Bagian **Rumusan kandidat statistik hari ini** memberi peringkat kombinasi 4 digit dari frekuensi per posisi berbobot waktu (bobot 0,97 untuk setiap langkah ke belakang) dengan smoothing 1.
- Model menggunakan hasil HK yang valid saja; SGP dan SDY tidak dicampur ke model HK.
- Skor kandidat adalah skor relatif dalam model, bukan probabilitas menang. Hasil undian acak tidak dapat dipastikan dari arsip.
- Arsip awal berisi contoh yang dimasukkan pengguna dan belum dianggap tervalidasi otomatis sampai workflow berhasil membaca sumber.
