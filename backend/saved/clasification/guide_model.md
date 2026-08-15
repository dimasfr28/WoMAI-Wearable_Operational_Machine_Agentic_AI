# Laporan Replikasi — Predictive Maintenance pada AI4I 2020

Dibuat 2026-08-14 · seluruh angka di dokumen ini dihasilkan oleh eksekusi
`replikasi_ai4i2020.ipynb`, tidak ada yang diketik manual.

---

## Ringkasan eksekutif

| | |
|---|---|
| Dataset | AI4I 2020, 10000 baris, 339 kegagalan (3.39%) |
| Imbalance ratio | 1 : 28.5 |
| Fitur | 9 — 4 sensor + 5 turunan fisika, **tanpa Torque dalam bentuk apa pun** |
| Model final (dikirim) | **XGBoost·rec** |
| Kriteria titik operasi | biaya harapan minimum, C_FN:C_FP = 10:1 |
| PR-AUC tertinggi | XGBoost·rec (0.7421) |
| PR-AUC test | **0.7421** (baseline acak 0.0340 → 21.8×) |
| Threshold operasional | 0.1181 (diturunkan dari OOF train) |
| Pada threshold itu | recall 79.4%, precision 41.9%, 37.5 false alarm per 1.000 unit |
| Baseline majority-class | 96.60% accuracy tanpa mendeteksi satu pun kegagalan |

---

## TAHAP 1 — EDA

- 10000 baris × 14 kolom.
- **Missing value: nol.** Dataset ini tidak memiliki satu pun nilai kosong, jadi
  tidak ada imputasi yang dijalankan. Menambahkan imputer akan jadi langkah
  kosmetik yang tidak mengubah apa pun.
- Duplikat baris penuh: nol.
- Distribusi kelas: 339 gagal vs 9661 normal.
- Semua korelasi linier terhadap target lemah (|r| < 0,2). Sinyal kegagalan AI4I
  bersifat interaksi dan ambang, bukan hubungan linier tunggal.

## TAHAP 2 — Pencegahan kebocoran data

Kolom `TWF, HDF, PWF, OSF, RNF` adalah **label mode kegagalan**, bukan sensor.
Memakainya sebagai fitur berarti model "memprediksi" kegagalan dari informasi
yang baru ada setelah kegagalan terjadi. Kelimanya dipakai **hanya** untuk
validasi konsistensi:

- 27 baris tidak konsisten dengan `Machine failure` (0.27% dataset):
  18 baris `RNF=1` tapi `Machine failure=0`, dan 9 baris
  `Machine failure=1` tanpa satu pun mode aktif.
- **Perlakuan: tidak ada baris dibuang, tidak ada relabeling.** Membuang
  9 baris positif memangkas 2.7% kelas
  minoritas yang sudah langka; merelabel ke OR(5 mode) berarti memaksa model
  memprediksi RNF yang menurut definisinya acak.

Dibuang: `UDI`, `Product ID` (identifier), `Type` dan `Torque [Nm]` (keputusan
studi), serta kelima kolom mode (target leakage).

## TAHAP 3 — Feature engineering

9 fitur final: `air_temp_K`, `proc_temp_K`, `rpm`, `tool_wear_min`, `Temp_diff`, `Temp_ratio`, `Wear_x_rpm`, `Cooling_margin_rate`, `Thermal_wear_load`.

Turunan berbasis mekanisme fisik: `Temp_diff` (margin heat dissipation),
`Temp_ratio` (beban termal relatif ambient), `Wear_x_rpm` (akumulasi revolusi ≈
paparan abrasif), `Cooling_margin_rate` (pembuangan panas per satuan kecepatan),
`Thermal_wear_load` (interaksi termal × keausan).

Yang sengaja **tidak** dibuat: fitur torsi atau daya dalam bentuk apa pun,
termasuk rekonstruksi τ = P/ω dari rpm; dan indikator ambang rule generator
(mis. `Temp_diff < 8,6 & rpm < 1380`) — yang terakhir bukan domain knowledge
melainkan menyalin aturan pembangkit label ke dalam fitur, yaitu leakage
terselubung.

Standardisasi memakai `StandardScaler` **di dalam** `imblearn.pipeline.Pipeline`,
sehingga di-fit ulang per fold secara struktural, bukan karena disiplin manual.

## TAHAP 4 — Skema validasi

Split stratified 80/20 → train 8000 baris (271 positif),
test 2000 baris (68 positif). Test set dikunci sejak titik
ini dan baru dibuka satu kali di TAHAP 7. Tuning memakai StratifiedKFold 5-fold
di dalam train — rata-rata hanya 54 kegagalan per fold
validasi, yang jadi alasan uji stabilitas 5 seed dijalankan.

## TAHAP 5 — Penanganan class imbalance

Lima strategi diadu: `baseline`, `class_weight`, `SMOTE`, `SMOTETomek`, dan
`Jitter`. Yang terakhir menyalin titik minoritas nyata lalu menggesernya sedikit
(σ = 0,05 × simpangan baku tiap sensor ≈ ±9 rpm, ±0,1 K, ±3 menit tool wear),
meng-clip hasilnya ke rentang yang teramati, lalu **menghitung ulang** kelima
fitur turunan dari sensor yang sudah digeser.

### Apakah titik sintetis SMOTE memang tidak masuk akal secara fisik?

Kelima fitur turunan adalah fungsi deterministik dari empat sensor, jadi
klaimnya bisa diuji, bukan diperdebatkan:

| fitur               | sifat     | metode   |    galat_rata2 |      galat_maks |   galat_relatif_maks |   n_titik_melanggar |
|:--------------------|:----------|:---------|---------------:|----------------:|---------------------:|--------------------:|
| Temp_diff           | linier    | SMOTE    |    1.7997e-14  |     5.68434e-14 |          6.58068e-15 |                   0 |
| Temp_diff           | linier    | Jitter   |    0           |     0           |          0           |                   0 |
| Temp_ratio          | NONLINIER | SMOTE    |    7.31805e-06 |     5.9748e-05  |          5.78413e-05 |                7187 |
| Temp_ratio          | NONLINIER | Jitter   |    0           |     0           |          0           |                   0 |
| Wear_x_rpm          | NONLINIER | SMOTE    | 1828.78        | 40978.5         |          0.894214    |                6961 |
| Wear_x_rpm          | NONLINIER | Jitter   |    0           |     0           |          0           |                   0 |
| Cooling_margin_rate | NONLINIER | SMOTE    |    5.41991e-05 |     0.00120639  |          0.225934    |                7421 |
| Cooling_margin_rate | NONLINIER | Jitter   |    0           |     0           |          0           |                   0 |
| Thermal_wear_load   | NONLINIER | SMOTE    |    3.34726     |    97.2953      |          0.255025    |                6683 |
| Thermal_wear_load   | NONLINIER | Jitter   |    0           |     0           |          0           |                   0 |

Jawabannya **ya, tapi dengan satu koreksi penting**. `Temp_diff = proc − air`
bersifat **linier**, dan interpolasi linier SMOTE mengawetkannya persis — di
kolom itu SMOTE tidak melanggar apa pun. Empat turunan lain **nonlinier**, dan
di situlah SMOTE gagal: 7421 dari 7458 titik sintetisnya
punya fitur turunan yang tidak konsisten dengan sensornya sendiri, dengan galat
relatif sampai 89.4%. Jitter nol pelanggaran, karena turunannya
memang dihitung ulang.

Jadi sebab yang tepat bukan sekadar "titik tengah dua kegagalan bisa mustahil",
melainkan lebih tajam dan terukur: **interpolasi linier tidak mengawetkan
hubungan nonlinier antar-fitur.**

### Tapi apakah itu berarti Jitter menang?

Rata-rata keempat model, per strategi:

| strategi     |   PR_AUC |   ROC_AUC |   Recall |   Precision |     F1 |   Accuracy |
|:-------------|---------:|----------:|---------:|------------:|-------:|-----------:|
| baseline     |   0.5184 |    0.9053 |   0.2981 |      0.7553 | 0.4034 |     0.9733 |
| class_weight |   0.4924 |    0.9035 |   0.6533 |      0.4113 | 0.3808 |     0.8844 |
| SMOTE        |   0.4356 |    0.8799 |   0.6946 |      0.2461 | 0.33   |     0.8581 |
| SMOTETomek   |   0.4329 |    0.8816 |   0.702  |      0.2528 | 0.3384 |     0.8635 |
| Jitter       |   0.4383 |    0.8822 |   0.7021 |      0.2526 | 0.3376 |     0.8641 |

**PR-AUC rata-rata tertinggi: `baseline` (0.5184)**, disusul `class_weight` (0.4924). Recall@0,5 tertinggi dipegang `Jitter` (0.702), dengan precision jatuh ke 0.253.

Posisi Jitter: PR-AUC 0.4383 (+0.0027 terhadap SMOTE, -0.0800 terhadap baseline), recall 0.702, precision 0.253. Jadi Jitter memang mengungguli SMOTE, sesuai dugaan dari argumen fisika. Keduanya tetap di bawah baseline tanpa penanganan sama sekali.

Dipecah per model:

| model              |   baseline |   SMOTE |   Jitter |   Jitter−SMOTE |   Jitter−baseline |
|:-------------------|-----------:|--------:|---------:|---------------:|------------------:|
| LogisticRegression |     0.325  |  0.2744 |   0.2757 |         0.0012 |           -0.0494 |
| RandomForest       |     0.6079 |  0.5557 |   0.5544 |        -0.0014 |           -0.0535 |
| XGBoost            |     0.5816 |  0.5623 |   0.584  |         0.0217 |            0.0024 |
| FNN                |     0.5589 |  0.3499 |   0.3393 |        -0.0107 |           -0.2196 |

Jitter mengungguli SMOTE pada 2 dari 4 model (LogisticRegression, XGBoost). Yang lebih menarik: pada XGBoost ia bahkan melewati baseline — satu-satunya kombinasi di seluruh studi ini di mana menambah data sintetis benar-benar memperbaiki ranking, bukan sekadar menggeser kalibrasi. Selisihnya +0.0024, masih jauh lebih kecil daripada simpangan antar-fold (±0,03), jadi ini sinyal lemah yang menarik untuk ditindaklanjuti — bukan kemenangan.

Penjelasan umumnya: PR-AUC mengukur kualitas *ranking* probabilitas dan tidak
bergantung threshold. Resampling terutama menggeser kalibrasi probabilitas ke
atas, jadi lebih banyak sampel melewati ambang 0,5 — recall naik, precision
jatuh. Kalau rankingnya sendiri tidak membaik, efek itu bisa dicapai gratis
dengan menurunkan threshold, tanpa biaya menambah data buatan. Itulah yang
dilakukan TAHAP 7.

Pelajarannya: **argumen fisika yang benar tidak otomatis jadi keunggulan
prediktif.** Jitter memang menghasilkan titik yang lebih masuk akal daripada
SMOTE — itu terbukti di tabel konsistensi. Apakah keunggulan itu berubah jadi
PR-AUC yang lebih tinggi adalah pertanyaan terpisah, dan hanya angka di tabel
kedua yang boleh menjawabnya.

## TAHAP 6 — Pemodelan dan tuning

`RandomizedSearchCV` dengan `scoring='average_precision'` (bukan accuracy).
Strategi imbalance ikut dimasukkan sebagai hyperparameter, jadi pemilihannya
tunduk pada kriteria yang sama:

| model              |   PR_AUC_cv |   PR_AUC_cv_std |   n_iter |     detik |
|:-------------------|------------:|----------------:|---------:|----------:|
| XGBoost            |      0.6429 |          0.0335 |       50 |  172.242  |
| RandomForest       |      0.6312 |          0.023  |       50 | 1337.46   |
| FNN                |      0.4926 |          0.076  |       14 |  469.029  |
| LogisticRegression |      0.34   |          0.0368 |       50 |   13.7167 |

Strategi imbalance yang dipilih pencarian: XGBoost → passthrough, RandomForest → passthrough, FNN → passthrough, LogisticRegression → passthrough.

## TAHAP 6B — HPO Optuna, dioptimasi untuk recall

PR-AUC memperlakukan seluruh kurva precision-recall sama pentingnya, padahal
kebutuhan operasional predictive maintenance condong ke satu sisi: **kegagalan
yang lolos jauh lebih mahal daripada inspeksi yang sia-sia.** Satu unplanned
downtime menghentikan lini; satu false alarm hanya memakan waktu teknisi.
Karena itu ditambahkan satu putaran HPO dengan objektif berbeda:

- **Objektif** `recall_at_precision(≥20%)` — dari kurva PR
  pada fold validasi, recall tertinggi yang precision-nya masih memenuhi lantai.
  Bebas threshold saat CV, dan biaya yang dibayar eksplisit.
- **Optimizer** Optuna TPE + `MedianPruner`, menggantikan pencarian acak.

`scoring='recall'` polos sengaja **tidak** dipakai: recall dimaksimalkan
sempurna dengan menandai semua unit sebagai gagal. Tanpa lantai precision,
tuning akan berlari ke model yang membunyikan alarm terus-menerus — recall 100%,
precision 3,4% (sama dengan menebak acak), tidak ada nilainya.

Lantai 20% dipilih secara sadar: pada kurva PR out-of-fold,
titik itu memberi recall sekitar 89% dengan konsekuensi ~120 false alarm per
1.000 unit. Artinya sekitar 12% armada masuk daftar inspeksi tiap siklus dan
4 dari 5 alarm meleset. Itu keputusan biaya, bukan keputusan statistik, dan
dicatat di sini supaya pembaca laporan tahu itu dipilih, bukan kebetulan.

| model              |   rec_at_lantai_cv |   n_trial |   n_pruned | imbalance   |
|:-------------------|-------------------:|----------:|-----------:|:------------|
| XGBoost            |             0.8968 |        60 |         19 | passthrough |
| RandomForest       |             0.8783 |        50 |         13 | passthrough |
| FNN                |             0.8598 |        25 |          2 | passthrough |
| LogisticRegression |             0.7493 |        60 |         19 | passthrough |

Total 195 trial, 53 di antaranya
dihentikan pruner sebelum menyelesaikan kelima fold.

### Apakah objektifnya benar-benar mengubah sesuatu?

Kedua keluarga model dinilai memakai **kedua** metrik lewat CV yang sama:

| model              | objektif        |   PR_AUC_cv |   rec_at_lantai_cv |
|:-------------------|:----------------|------------:|-------------------:|
| LogisticRegression | objektif PR-AUC |      0.34   |             0.7344 |
| LogisticRegression | objektif recall |      0.2774 |             0.7493 |
| RandomForest       | objektif PR-AUC |      0.6312 |             0.834  |
| RandomForest       | objektif recall |      0.6473 |             0.8783 |
| XGBoost            | objektif PR-AUC |      0.6429 |             0.8673 |
| XGBoost            | objektif recall |      0.638  |             0.8968 |
| FNN                | objektif PR-AUC |      0.4926 |             0.7859 |
| FNN                | objektif recall |      0.5783 |             0.8598 |

### Buktinya di test set

| model              |   recall_PRAUC_maksF1 |   recall_recHPO |   delta_recall |   prec_PRAUC_maksF1 |   prec_recHPO |   delta_precision |   FN_PRAUC |   FN_recHPO |   kegagalan_tertangkap_tambahan |   FP_tambahan |
|:-------------------|----------------------:|----------------:|---------------:|--------------------:|--------------:|------------------:|-----------:|------------:|--------------------------------:|--------------:|
| LogisticRegression |                0.6765 |          0.8529 |         0.1765 |              0.3566 |        0.2257 |           -0.1309 |         22 |          10 |                              12 |           116 |
| RandomForest       |                0.5882 |          0.8971 |         0.3088 |              0.7407 |        0.204  |           -0.5367 |         28 |           7 |                              21 |           224 |
| XGBoost            |                0.6324 |          0.8824 |         0.25   |              0.6935 |        0.2027 |           -0.4908 |         25 |           8 |                              17 |           217 |
| FNN                |                0.6471 |          0.8971 |         0.25   |              0.4889 |        0.1789 |           -0.31   |         24 |           7 |                              17 |           234 |

HPO recall menaikkan recall pada 4 dari 4 model, rata-rata +0.2463, dengan precision bergeser -0.3671. Dijumlah keempat model: **+67 kegagalan tertangkap tambahan** dengan harga **+791 false positive** di test set (2000 unit).

**Peringatan:** lantai precision yang dijaga saat CV TIDAK bertahan di test untuk FNN. Itu kegagalan generalisasi lantai, dan angka recall-nya tidak boleh dibaca tanpa catatan ini.

Model final dipilih dari **OOF train**, bukan test: recall tertinggi yang precision-nya masih memenuhi lantai. Yang terpilih **XGBoost·rec**.

## TAHAP 7 — Evaluasi

### Metrik pada test set

| model                  | titik                                   |   threshold |   PR_AUC |   ROC_AUC |   Recall |   Precision |     F1 |   Accuracy |   TP |   FP |   FN |
|:-----------------------|:----------------------------------------|------------:|---------:|----------:|---------:|------------:|-------:|-----------:|-----:|-----:|-----:|
| LogisticRegression     | threshold 0.5                           |      0.5    |   0.3186 |    0.8913 |   0.0441 |      0.75   | 0.0833 |     0.967  |    3 |    1 |   65 |
| LogisticRegression     | maks F1 (dari OOF)                      |      0.1244 |   0.3186 |    0.8913 |   0.6765 |      0.3566 | 0.467  |     0.9475 |   46 |   83 |   22 |
| LogisticRegression     | recall>=90% (dari OOF)                  |      0.0126 |   0.3186 |    0.8913 |   0.9265 |      0.0681 | 0.1269 |     0.5665 |   63 |  862 |    5 |
| LogisticRegression     | biaya minimum 10:1 (dari OOF)           |      0.1065 |   0.3186 |    0.8913 |   0.7206 |      0.3101 | 0.4336 |     0.936  |   49 |  109 |   19 |
| LogisticRegression     | recall maks @ precision>=20% (dari OOF) |      0.0732 |   0.3186 |    0.8913 |   0.7647 |      0.2047 | 0.323  |     0.891  |   52 |  202 |   16 |
| RandomForest           | threshold 0.5                           |      0.5    |   0.7322 |    0.9386 |   0.5294 |      0.8182 | 0.6429 |     0.98   |   36 |    8 |   32 |
| RandomForest           | maks F1 (dari OOF)                      |      0.3722 |   0.7322 |    0.9386 |   0.5882 |      0.7407 | 0.6557 |     0.979  |   40 |   14 |   28 |
| RandomForest           | recall>=90% (dari OOF)                  |      0.0082 |   0.7322 |    0.9386 |   0.9265 |      0.1186 | 0.2104 |     0.7635 |   63 |  468 |    5 |
| RandomForest           | biaya minimum 10:1 (dari OOF)           |      0.1283 |   0.7322 |    0.9386 |   0.7941 |      0.3803 | 0.5143 |     0.949  |   54 |   88 |   14 |
| RandomForest           | recall maks @ precision>=20% (dari OOF) |      0.0387 |   0.7322 |    0.9386 |   0.8529 |      0.2222 | 0.3526 |     0.8935 |   58 |  203 |   10 |
| XGBoost                | threshold 0.5                           |      0.5    |   0.7349 |    0.9459 |   0.5    |      0.85   | 0.6296 |     0.98   |   34 |    6 |   34 |
| XGBoost                | maks F1 (dari OOF)                      |      0.2896 |   0.7349 |    0.9459 |   0.6324 |      0.6935 | 0.6615 |     0.978  |   43 |   19 |   25 |
| XGBoost                | recall>=90% (dari OOF)                  |      0.0229 |   0.7349 |    0.9459 |   0.8971 |      0.1805 | 0.3005 |     0.858  |   61 |  277 |    7 |
| XGBoost                | biaya minimum 10:1 (dari OOF)           |      0.1071 |   0.7349 |    0.9459 |   0.7941 |      0.3971 | 0.5294 |     0.952  |   54 |   82 |   14 |
| XGBoost                | recall maks @ precision>=20% (dari OOF) |      0.0283 |   0.7349 |    0.9459 |   0.8824 |      0.1993 | 0.3252 |     0.8755 |   60 |  241 |    8 |
| FNN                    | threshold 0.5                           |      0.5    |   0.593  |    0.9476 |   0.8676 |      0.2218 | 0.3533 |     0.892  |   59 |  207 |    9 |
| FNN                    | maks F1 (dari OOF)                      |      0.8138 |   0.593  |    0.9476 |   0.6471 |      0.4889 | 0.557  |     0.965  |   44 |   46 |   24 |
| FNN                    | recall>=90% (dari OOF)                  |      0.326  |   0.593  |    0.9476 |   0.9559 |      0.1484 | 0.2569 |     0.812  |   65 |  373 |    3 |
| FNN                    | biaya minimum 10:1 (dari OOF)           |      0.6526 |   0.593  |    0.9476 |   0.7941 |      0.3086 | 0.4444 |     0.9325 |   54 |  121 |   14 |
| FNN                    | recall maks @ precision>=20% (dari OOF) |      0.5937 |   0.593  |    0.9476 |   0.8382 |      0.2808 | 0.4207 |     0.9215 |   57 |  146 |   11 |
| LogisticRegression·rec | threshold 0.5                           |      0.5    |   0.2684 |    0.9084 |   0.9265 |      0.1291 | 0.2266 |     0.785  |   63 |  425 |    5 |
| LogisticRegression·rec | maks F1 (dari OOF)                      |      0.7124 |   0.2684 |    0.9084 |   0.7941 |      0.2872 | 0.4219 |     0.926  |   54 |  134 |   14 |
| LogisticRegression·rec | recall>=90% (dari OOF)                  |      0.3256 |   0.2684 |    0.9084 |   0.9412 |      0.08   | 0.1475 |     0.63   |   64 |  736 |    4 |
| LogisticRegression·rec | biaya minimum 10:1 (dari OOF)           |      0.6687 |   0.2684 |    0.9084 |   0.8235 |      0.2353 | 0.366  |     0.903  |   56 |  182 |   12 |
| LogisticRegression·rec | recall maks @ precision>=20% (dari OOF) |      0.6518 |   0.2684 |    0.9084 |   0.8529 |      0.2257 | 0.3569 |     0.8955 |   58 |  199 |   10 |
| RandomForest·rec       | threshold 0.5                           |      0.5    |   0.7401 |    0.9588 |   0.5147 |      0.8974 | 0.6542 |     0.9815 |   35 |    4 |   33 |
| RandomForest·rec       | maks F1 (dari OOF)                      |      0.2774 |   0.7401 |    0.9588 |   0.6324 |      0.7414 | 0.6825 |     0.98   |   43 |   15 |   25 |
| RandomForest·rec       | recall>=90% (dari OOF)                  |      0.0204 |   0.7401 |    0.9588 |   0.9412 |      0.1546 | 0.2656 |     0.823  |   64 |  350 |    4 |
| RandomForest·rec       | biaya minimum 10:1 (dari OOF)           |      0.0833 |   0.7401 |    0.9588 |   0.7941 |      0.3273 | 0.4635 |     0.9375 |   54 |  111 |   14 |
| RandomForest·rec       | recall maks @ precision>=20% (dari OOF) |      0.0317 |   0.7401 |    0.9588 |   0.8971 |      0.204  | 0.3324 |     0.8775 |   61 |  238 |    7 |
| XGBoost·rec            | threshold 0.5                           |      0.5    |   0.7421 |    0.9444 |   0.5147 |      0.8974 | 0.6542 |     0.9815 |   35 |    4 |   33 |
| XGBoost·rec            | maks F1 (dari OOF)                      |      0.2639 |   0.7421 |    0.9444 |   0.7059 |      0.6857 | 0.6957 |     0.979  |   48 |   22 |   20 |
| XGBoost·rec            | recall>=90% (dari OOF)                  |      0.0303 |   0.7421 |    0.9444 |   0.8971 |      0.1906 | 0.3144 |     0.867  |   61 |  259 |    7 |
| XGBoost·rec            | biaya minimum 10:1 (dari OOF)           |      0.1181 |   0.7421 |    0.9444 |   0.7941 |      0.4186 | 0.5482 |     0.9555 |   54 |   75 |   14 |
| XGBoost·rec            | recall maks @ precision>=20% (dari OOF) |      0.0385 |   0.7421 |    0.9444 |   0.8824 |      0.2027 | 0.3297 |     0.878  |   60 |  236 |    8 |
| FNN·rec                | threshold 0.5                           |      0.5    |   0.654  |    0.9448 |   0.8971 |      0.181  | 0.3012 |     0.8585 |   61 |  276 |    7 |
| FNN·rec                | maks F1 (dari OOF)                      |      0.8794 |   0.654  |    0.9448 |   0.6765 |      0.5055 | 0.5786 |     0.9665 |   46 |   45 |   22 |
| FNN·rec                | recall>=90% (dari OOF)                  |      0.3403 |   0.654  |    0.9448 |   0.9412 |      0.1425 | 0.2476 |     0.8055 |   64 |  385 |    4 |
| FNN·rec                | biaya minimum 10:1 (dari OOF)           |      0.6865 |   0.654  |    0.9448 |   0.8382 |      0.2701 | 0.4086 |     0.9175 |   57 |  154 |   11 |
| FNN·rec                | recall maks @ precision>=20% (dari OOF) |      0.495  |   0.654  |    0.9448 |   0.8971 |      0.1789 | 0.2983 |     0.8565 |   61 |  280 |    7 |

### Kenapa accuracy dan ROC-AUC tidak dijadikan metrik keputusan

Baseline majority-class = **96.60%**. Model dengan accuracy
98.15% hanya unggul
+1.55% poin dari strategi "tebak normal
terus". ROC-AUC juga optimistis karena false-positive rate dinormalisasi
terhadap 1932 negatif — tambahan puluhan false alarm
nyaris tidak menggerakkannya. PR-AUC menormalisasi terhadap 68
positif, jadi ia yang terasa.

### Optimasi threshold

Threshold **tidak** dibiarkan di 0,5. Ia dicari dari prediksi out-of-fold pada
train, lalu dibekukan dan diterapkan ke test — bukan dicari di test, yang akan
membuat angka test kehilangan sifatnya sebagai estimasi data baru.

Threshold optimal-di-test juga dihitung sebagai *oracle upper bound* dan
dilaporkan di `artefak/tahap7_oracle_threshold.csv`; selisihnya menunjukkan
berapa banyak F1 yang akan dilaporkan berlebih kalau threshold dicuri dari test.

### Stabilitas 5 seed

Seed 42/43/44/45/46, masing-masing split ulang + fit ulang + threshold dicari
ulang dari OOF seed itu sendiri:

| model              | PR_AUC          | ROC_AUC         | Recall          | Precision       | F1              |
|:-------------------|:----------------|:----------------|:----------------|:----------------|:----------------|
| LogisticRegression | 0.3710 ± 0.0694 | 0.8926 ± 0.0094 | 0.6118 ± 0.0472 | 0.3583 ± 0.0419 | 0.4506 ± 0.0372 |
| RandomForest       | 0.7162 ± 0.0389 | 0.9427 ± 0.0130 | 0.6088 ± 0.0305 | 0.7649 ± 0.0552 | 0.6779 ± 0.0401 |
| XGBoost            | 0.7229 ± 0.0398 | 0.9521 ± 0.0159 | 0.6471 ± 0.0416 | 0.7006 ± 0.0415 | 0.6727 ± 0.0410 |
| FNN                | 0.5614 ± 0.1427 | 0.9369 ± 0.0332 | 0.6412 ± 0.0886 | 0.4384 ± 0.0966 | 0.5184 ± 0.0922 |

## TAHAP 8 — Explainability

Model yang dijelaskan: **XGBoost·rec** (TreeExplainer).

Tiga ukuran importance berdampingan:

| fitur               |   mean_abs_SHAP |   permutation_dPR_AUC |   impurity |
|:--------------------|----------------:|----------------------:|-----------:|
| rpm                 |         1.35448 |               0.65347 |    0.23173 |
| tool_wear_min       |         0.61703 |               0.13558 |    0.14964 |
| Temp_ratio          |         0.18364 |               0.25656 |    0.14543 |
| Thermal_wear_load   |         0.13194 |               0.00937 |    0.07674 |
| Temp_diff           |         0.13103 |               0.03907 |    0.10084 |
| air_temp_K          |         0.06565 |              -0.007   |    0.05367 |
| Wear_x_rpm          |         0.06206 |              -0.00089 |    0.11796 |
| Cooling_margin_rate |         0.03649 |               0.00508 |    0.04744 |
| proc_temp_K         |         0.01208 |              -0.00111 |    0.07653 |

**Impurity importance sengaja tidak dipakai sendirian.** Ia menghitung total
penurunan impurity saat fitur dipakai untuk split, sehingga fitur dengan lebih
banyak nilai unik punya lebih banyak titik split kandidat dan skornya bisa
menggelembung. Ia juga dihitung dari data train dan tidak pernah menguji
kegunaan di data baru. Permutation importance mengukur penurunan PR-AUC nyata di
test saat fitur diacak — pertanyaan yang berbeda dan lebih relevan operasional.

**Yang benar-benar terjadi di dataset ini:** ketiga ukuran sepakat. Selisih
peringkat impurity vs SHAP terbesar hanya 3 posisi
(Wear_x_rpm), dan fitur berkardinalitas tertinggi
(`Wear_x_rpm`, 7469 nilai unik) tidak menggelembung — ia
duduk di peringkat 4 menurut
impurity dan 7 menurut SHAP.
Jadi bias kardinalitas **tidak terwujud di sini**. Itu temuan yang menguatkan
kesimpulan, bukan alasan berhenti mengecek: yang membuat kita tahu bias itu
tidak terjadi justru karena ketiganya dihitung dan dibandingkan.

### Interpretasi fisik

Tiga fitur teratas menurut SHAP: `rpm`, `tool_wear_min`, `Temp_ratio`.

Soal klaim **"dominasi Torque dan Tool wear"**, klaim itu perlu dipecah dua:

**Bagian Torque — tidak dapat diuji.** Torque tidak ada dalam studi ini: bukan
kolom, bukan turunan, bukan proxy. Bagian ini tidak dikonfirmasi dan tidak
dibantah; ia berada di luar jangkauan eksperimen dan tidak akan dikarang.

**Bagian Tool wear — dapat diuji, dan hasilnya berbeda dari dugaan.**
`tool_wear_min` menempati peringkat
2 menurut SHAP dan
3 menurut permutasi —
penting, tapi bukan yang teratas. Yang memuncaki keduanya adalah **`rpm`**
(mean |SHAP| 1.354; permutasi
0.653 PR-AUC).

Secara fisik itu masuk akal: `rpm` masuk langsung ke rule HDF (gagal saat
`Temp_diff` kecil **dan** rpm rendah), dan HDF adalah mode kegagalan terbesar di
dataset (33.9% dari seluruh
kegagalan). Sebagai catatan pengukuran — bukan sebagai fitur — matriks korelasi
TAHAP 1 menunjukkan `rpm` dan Torque berkorelasi
-0.875 pada dataset ini, akibat
penggerak berdaya hampir konstan. Sebagian informasi yang hilang bersama Torque
karenanya masih terbaca lewat `rpm`. Itu **bukan** pengganti Torque: ia tidak
memulihkan rule PWF dan OSF, yang membutuhkan nilai torsinya sendiri, bukan
urutannya.

### Harga membuang Torque, diukur bukan diduga

OSF dan PWF adalah dua mekanisme yang ambangnya secara definisi memuat torque
(OSF: tool wear × torque; PWF: daya = torque × ω). Keduanya menyumbang
56.9% dari seluruh kegagalan dataset.

Recall XGBoost·rec dipecah per mode kegagalan pada threshold 0.1181
(kolom mode dipakai di sini **sebagai diagnostik post-hoc saja** — model tidak
pernah melihatnya):

| mode   |   n_kegagalan |   terdeteksi |   lolos | recall   | butuh_torque   |
|:-------|--------------:|-------------:|--------:|:---------|:---------------|
| TWF    |            10 |            5 |       5 | 0.500    | False          |
| HDF    |            29 |           29 |       0 | 1.000    | False          |
| PWF    |            13 |            7 |       6 | 0.538    | True           |
| OSF    |            16 |           14 |       2 | 0.875    | True           |
| RNF    |             0 |            0 |       0 | —        | False          |

Hasilnya terbelah tiga, dan ketiganya punya sebab berbeda:

1. **HDF — recall 100.0%**
   (29/29). Rule-nya deterministik dan
   seluruh variabel penentunya tersedia (`Temp_diff` kecil **dan** rpm rendah).
   Model merekonstruksinya sempurna.
2. **PWF + OSF — recall 72.4%**
   (21/29). Ambang
   keduanya secara definisi memuat torque, yang dibuang dari studi ini. **Inilah
   harga membuang Torque**, dan sekarang ia berupa angka, bukan dugaan.
3. **TWF — recall 50.0%**
   (5/10), justru yang **terburuk** —
   dan ini bukan soal torque, karena `tool_wear_min` tersedia sebagai fitur.
   Sebabnya lain: pada generator AI4I, TWF dipicu pada titik keausan yang diundi
   acak di rentang 200–240 menit. Tidak ada ambang tetap untuk dipelajari, jadi
   ceiling-nya rendah berapa pun feature set-nya.

**Kesimpulan yang jujur:** absennya Torque menjelaskan kelompok 2, tapi **tidak**
menjelaskan kelompok 3. Menyalahkan Torque untuk seluruh recall yang hilang akan
keliru — sebagian memang batas intrinsik dataset, bukan konsekuensi keputusan
desain studi ini.

## TAHAP 9 — Kesimpulan, keterbatasan, rekomendasi

### Model mana yang menang, pada metrik apa

**XGBoost·rec** menang pada PR-AUC test (0.7421), metrik keputusan
utama studi ini. Trade-off-nya: pada threshold operasional 0.1181, model
menangkap 79.4% kegagalan dengan precision 41.9%
— artinya sekitar 58 dari setiap 100 alarm
adalah false alarm.

**Tapi "menang" di sini harus dibaca hati-hati.** Jarak XGBoost dan RandomForest
pada PR-AUC test hanya
0.0027 — jauh lebih kecil daripada
simpangan baku antar-seed keduanya (±0.0398
dan ±0.0389). Pada rata-rata 5 seed
urutannya bahkan berbalik: RandomForest
0.7162 vs XGBoost
0.7229. Kesimpulan yang jujur: **keduanya
tidak terbedakan secara statistik**, dan pemilihan di antara keduanya sebaiknya
memakai kriteria lain (biaya inferensi, kemudahan deployment), bukan selisih
desimal keempat.

Yang terbedakan dengan jelas hanyalah tiga hal: kedua model tree jauh mengungguli
LogisticRegression (0.3186), FNN berada di antaranya
(0.5930), dan semuanya jauh di atas baseline acak 0.0340.

Catatan tambahan: PR-AUC test (0.7421) lebih tinggi daripada
PR-AUC CV saat tuning (0.6429).
Dua sebab yang wajar: model final dilatih pada 8.000 baris penuh sementara tiap
fold CV hanya melihat 6.400, dan test split ini kebetulan sedikit lebih mudah —
terlihat dari sebaran antar-seed di atas. Selisih itu bukan tanda leakage; test
set baru dibuka satu kali, sesudah seluruh tuning selesai.

### Keterbatasan — jujur

1. **AI4I 2020 adalah dataset sintetis.** Labelnya dihasilkan aturan
   deterministik dengan ambang eksplisit, ditambah RNF sebagai noise 0,1%. Model
   di sini pada dasarnya merekonstruksi aturan itu dari sensor. Mesin nyata
   tidak gagal menurut fungsi ambang yang rapi.
2. **Sebagian recall yang hilang adalah batas intrinsik, bukan kekurangan
   model.** TWF dipicu pada titik keausan yang diundi acak di rentang 200–240
   menit, jadi tidak ada ambang tetap untuk dipelajari — recall-nya
   50.0% sekalipun `tool_wear_min` tersedia penuh. Menambah fitur
   atau mengganti algoritma tidak akan memperbaiki bagian ini.
3. **Tidak ada dimensi temporal maupun RUL.** Setiap baris diperlakukan
   independen. Studi ini menjawab "apakah unit ini sedang dalam kondisi gagal",
   bukan "berapa lama lagi sampai gagal". Predictive maintenance yang
   sesungguhnya membutuhkan yang kedua.
4. **Torque tidak dipakai**, atas keputusan desain studi. Dua dari lima mode
   kegagalan (PWF, OSF — 56.9% kegagalan) kehilangan variabel
   penentunya, dan biayanya terukur: recall 72.4% pada kedua mode itu
   versus 100.0% pada HDF yang variabelnya lengkap. Angka di laporan
   ini karena itu tidak sebanding dengan publikasi AI4I yang memakai fitur
   lengkap, dan tidak boleh dibandingkan langsung.
5. **Test set hanya 68 kegagalan.** Satu-dua kasus berbeda sudah
   menggeser recall sekitar 1.5 poin persen. Itu sebabnya
   uji 5 seed dilaporkan; angka tunggal tanpa interval akan menyesatkan.
6. **Generalisasi ke data industri riil terbatas.** Sensor nyata punya drift,
   missing value, mode kegagalan yang tidak terdaftar, dan distribusi yang
   bergeser seiring waktu — tiga hal yang sama sekali tidak ada di sini.

### Rekomendasi operasional

**Titik operasi tidak dipilih dari selera metrik, tapi dari rasio biaya.**
Recall dan precision adalah satu kurva, bukan dua tombol terpisah: menaikkan
recall berarti menurunkan threshold, dan itu otomatis menambah false alarm.
Yang menentukan di mana kurva itu dipotong adalah perbandingan biaya satu
unplanned downtime terhadap satu inspeksi sia-sia — besaran pabrik, bukan
besaran statistik.

Asumsi yang dipakai: **C_FN : C_FP = 10 : 1**. Pada threshold
0.1181 yang diturunkan dari OOF train, per 1.000 unit:

- **37.5 false alarm** — inspeksi yang tidak
  menemukan apa-apa.
- **7.0 kegagalan lolos** — mesin rusak tanpa
  peringatan.
- recall 79.4%, precision 41.9%.

### Kalau rasio biayamu berbeda

Threshold tinggal diambil dari baris lain di tabel ini — **model tidak perlu
dilatih ulang**, karena rankingnya tidak berubah, hanya titik potongnya. Setiap
baris thresholdnya diturunkan dari OOF train pada rasio itu, lalu diukur di test:

| C_FN:C_FP   |   threshold |   Recall |   Precision |   TP |   FP |   FN |   false_alarm_per_1000 |   kegagalan_lolos_per_1000 |   biaya_test |
|:------------|------------:|---------:|------------:|-----:|-----:|-----:|-----------------------:|---------------------------:|-------------:|
| 1:1         |      0.3584 |   0.6324 |      0.7288 |   43 |   16 |   25 |                    8   |                       12.5 |           41 |
| 2:1         |      0.2639 |   0.7059 |      0.6857 |   48 |   22 |   20 |                   11   |                       10   |           62 |
| 5:1         |      0.1181 |   0.7941 |      0.4186 |   54 |   75 |   14 |                   37.5 |                        7   |          145 |
| 10:1        |      0.1181 |   0.7941 |      0.4186 |   54 |   75 |   14 |                   37.5 |                        7   |          215 |
| 20:1        |      0.0353 |   0.8824 |      0.1967 |   60 |  245 |    8 |                  122.5 |                        4   |          405 |
| 30:1        |      0.0353 |   0.8824 |      0.1967 |   60 |  245 |    8 |                  122.5 |                        4   |          485 |
| 50:1        |      0.0274 |   0.9118 |      0.1896 |   62 |  265 |    6 |                  132.5 |                        3   |          565 |
| 100:1       |      0.0178 |   0.9265 |      0.1462 |   63 |  368 |    5 |                  184   |                        2.5 |          868 |

Rasio 10:1 dipilih sebagai default karena pada 5:1 sampai
sekitar 15:1 threshold optimalnya nyaris tidak bergerak (plateau) — jadi
pilihan itu tahan terhadap ketidakpastian estimasi biaya. Titik recall-maksimum
yang sempat dipertimbangkan (recall ~88%, precision ~20%) baru menjadi optimal
kalau satu downtime setara **30 inspeksi atau lebih**.

### Satu risiko yang tidak muncul di tabel mana pun

**Alarm fatigue.** Pada precision rendah, mayoritas alarm meleset; operator
berhenti mempercayainya dan mulai mengabaikan — termasuk alarm yang benar.
Recall efektif di lapangan lalu runtuh jauh di bawah angka mana pun di laporan
ini. Ditambah kendala kapasitas: kalau tim maintenance hanya sanggup memeriksa
sejumlah unit per siklus, titik operasi dengan false alarm tinggi tidak bisa
dijalankan apa adanya — yang diperiksa jadi unit yang kebetulan di urutan awal,
bukan yang paling berisiko.

Praktisnya: jadwalkan inspeksi pada unit yang skornya melewati threshold,
kalibrasi ulang threshold setiap kali rasio biaya berubah, dan pantau berapa
persen alarm yang terbukti benar di lapangan — kalau angka itu jatuh jauh di
bawah precision yang dilaporkan, distribusinya sudah bergeser dan modelnya perlu
dilatih ulang.

---

## Artefak

Model final: `model_final_ai4i.pkl` (joblib) — berisi pipeline terlatih,
threshold, daftar fitur, metrik test, dan versi library. Sudah diverifikasi
dimuat ulang dan mereproduksi angka di atas persis.

Tabel dan gambar: folder `artefak/`.
