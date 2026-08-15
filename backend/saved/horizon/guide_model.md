# Case 1 — Model Prediksi Failure Berhorizon Waktu

File model: `case1_horizon_model.pkl`
Dibuat oleh: `model_horizon_kedua.ipynb` §2.6 (script cadangan: `export_case1_model.py`)
Versi: case1 / W=10 menit / notebook section 2

Model menjawab satu pertanyaan: **apakah mesin akan gagal dalam 10 menit ke depan?**

---

## 1. Cara pakai

```python
import pickle, pandas as pd

bundle = pickle.load(open("case1_horizon_model.pkl", "rb"))
model  = bundle["model"]
FEATS  = bundle["features"]      # ['air_temp_K','proc_temp_K','rpm','tool_wear_min']
THR    = bundle["threshold"]     # 0.477

skor  = model.predict_proba(X[FEATS])[:, 1]
alarm = skor >= THR              # True = gagal dalam 10 menit ke depan
```

`X` harus sudah melewati preprocessing di bagian 2. Tidak ada scaler yang perlu dimuat —
XGBoost bekerja pada nilai asli.

Isi bundle: `model`, `features`, `threshold`, `horizon_minutes`, `target`,
`cost_ratio_FN_FP`, `preprocessing`, `split`, `hyperparameters`, `test_metrics`.

---

## 2. Preprocessing

Urutannya wajib sama persis, karena `cycle` dan `delta_min` bergantung pada urutan baris.

```python
raw = pd.read_csv("ai4i2020.csv").sort_values("UDI").reset_index(drop=True)

# 1. tool cycle: tool wear naik monoton lalu reset saat tool diganti
raw["cycle"] = (raw["Tool wear [min]"].diff() < 0).cumsum()

# 2. durasi tiap baris, dari kenaikan tool wear (2 / 3 / 5 menit)
d = raw["Tool wear [min]"].diff()
raw["delta_min"] = d.where(d > 0, np.nan).fillna(3.0)   # titik reset & baris pertama -> 3.0

# 3. waktu berjalan
raw["t_min"] = raw["delta_min"].cumsum() - raw["delta_min"].iloc[0]

# 4. buang kolom
raw = raw.drop(columns=["Torque [Nm]", "Type", "TWF", "HDF", "PWF", "OSF", "RNF"])

# 5. rename
raw = raw.rename(columns={"Air temperature [K]": "air_temp_K",
                          "Process temperature [K]": "proc_temp_K",
                          "Rotational speed [rpm]": "rpm",
                          "Tool wear [min]": "tool_wear_min"})
```

Tidak ada scaling, tidak ada imputasi (AI4I tidak punya missing value), tidak ada
oversampling. Imbalance ditangani lewat `scale_pos_weight` di dalam model.

**Yang dibuang dan alasannya:**

| kolom | alasan |
|---|---|
| `Torque [Nm]` | diminta dibuang; lagipula autocorrelation ~0,005 (white noise) |
| `Type` / `Type_ord` | diminta dibuang |
| `TWF, HDF, PWF, OSF, RNF` | label mode; memakainya = kebocoran label |

---

## 3. Feature

Empat kolom, semuanya nilai sensor pada baris saat ini:

```
air_temp_K, proc_temp_K, rpm, tool_wear_min
```

Tidak ada rolling mean, tidak ada wear projection, tidak ada strain, tidak ada jam/menit.
Semuanya diuji lewat ablation dan **ditolak**.

`delta_min` tetap dibutuhkan saat preprocessing (untuk menyusun `t_min` dan `cycle`), tetapi
tidak masuk sebagai feature model.

**Aturan seleksi** (ditetapkan sebelum melihat hasil): di antara semua feature set yang
lift-nya berada dalam 1 sd dari yang terbaik, ambil yang **paling sedikit** featurenya. Tanpa
aturan ini, set terbesar hampir selalu menang karena noise — pada run ini "semua turunan"
(9 feature) memimpin dengan 2,869 padahal sd between-fold 1,001, jadi keunggulannya tidak
bermakna. Aturan yang sama dipakai untuk hyperparameter: ambil model paling sederhana di
antara yang setara.

---

## 4. Target

$$y_W(t) = 1 \iff \exists\, k \text{ dengan } t < t_k \le t + W \text{ menit, dalam tool cycle yang sama, } \texttt{Machine failure}(k) = 1$$

W = 10 menit. Window dimulai setelah baris saat ini, jadi baris tidak pernah masuk
targetnya sendiri. Window dipotong di batas tool cycle.

Beda dari notebook lama: di sana horizon dihitung dalam **baris** (H=10). Karena satu baris
memakan 2, 3, atau 5 menit, H=10 memberi lead time 20–37 menit yang berbeda-beda tiap
baris. Horizon menit membuat lead time seragam dan bisa dijanjikan ke operator.

---

## 5. Pemotongan train / test

Unit potong adalah **tool cycle**, bukan baris — supaya tidak ada cycle yang terbelah.
Potongan berbasis waktu, tidak diacak.

| bagian | cycle | baris | dipakai untuk |
|---|---|---|---|
| dev | 0–95 | 8112 | training + seleksi model, feature, hyperparameter |
| — threshold | 76–85 | ~800 | mengunci threshold (fold validasi terakhir) |
| test | 96–119 | 1888 | dibuka satu kali di akhir |

Seleksi memakai **rolling-origin CV** di dalam dev: train selalu di masa lalu, validasi di
periode berikutnya, origin digeser maju 5 kali (40/50%, 50/60%, … 80/90%). K-fold acak
tidak boleh dipakai di sini — mengacak baris berarti model belajar dari masa depan.

---

## 6. Hasil seluruh percobaan

### 6a. Ablation feature (rolling-origin CV, target W=10 menit)

| feature set | n | lift CV | sd |
|---|---|---|---|
| semua turunan | 9 | 2,869 | 1,044 |
| **4 sensor mentah** | **4** | **2,754** | 1,009 |
| + delta_min | 5 | 2,720 | 1,000 |
| + dT | 6 | 2,717 | 0,908 |
| + wear rate per menit | 7 | 2,691 | 1,045 |

Rentang antar-set 0,177 vs sd between-fold 1,001 — selisihnya enam kali lebih kecil dari
noise, jadi peringkat mentahnya tidak bermakna. Aturan parsimoni memilih 4 sensor mentah.

### 6b. Perbandingan model (feature set terpilih)

| model | lift CV | sd |
|---|---|---|
| **XGBoost** | **2,754** | 1,009 |
| ExtraTrees | 2,559 | 0,833 |
| RandomForest | 2,497 | 0,828 |
| HistGB | 2,274 | 0,792 |
| LogReg | 2,123 | 0,972 |

Selisih ke peringkat-2 (0,195) jauh lebih kecil dari sd (1,009), jadi peringkat teratas
harus dibaca "tak terbedakan", bukan "pemenang".

Tuning 24 kombinasi → `max_depth=3, lr=0.03, n_estimators=300, min_child_weight=5`.
Kapasitas lebih besar (depth 5/7, 600 pohon) tidak terbukti membantu.

### 6c. Tiga pendekatan yang dicoba dan gagal

| percobaan | alasan mencoba | hasil |
|---|---|---|
| feature stasioner | temperature random walk, levelnya mungkin spurious | CV menolak: 2,138 → 1,900 |
| monotone constraint | wear naik seharusnya tidak menurunkan risiko | turun di semua feature set (−0,02 … −0,11) |
| blend model + wear rule | rule menang di test, mungkin saling melengkapi | bobot optimal = 0, rule tidak menambah apapun |

Ketiganya diputuskan lewat CV; test tidak diintip.

### 6d. Sweep horizon W — hasil utama

| W (mnt) | prevalence | PR-AUC | lift | ROC-AUC | precision | recall | F1 | FN | FP | cost | wear rule | selalu alarm |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **10** | 0,055 | 0,279 | **5,06×** | **0,842** | 0,261 | 0,663 | 0,375 | 35 | 195 | **545** | 576 | 1784 |
| 20 | 0,108 | 0,330 | 3,07× | 0,770 | 0,211 | 0,709 | 0,326 | 59 | 537 | 1127 | 1109 | 1685 |
| 30 | 0,155 | 0,358 | 2,32× | 0,730 | 0,155 | 1,000 | 0,268 | 0 | 1594 | 1594 | 1169 | 1596 |
| 45 | 0,225 | 0,446 | 1,98× | 0,735 | 0,225 | 1,000 | 0,367 | 0 | 1463 | 1463 | 1221 | 1463 |
| 60 | 0,294 | 0,501 | 1,70× | 0,734 | 0,294 | 1,000 | 0,454 | 0 | 1333 | 1333 | 1270 | 1333 |

Pembanding untuk target berbasis baris (H=10): PR-AUC 0,3633, lift 2,55×, cost 1589 —
kalah dari wear rule (1124).

### 6e. Model final yang diekspor (W=10)

| | |
|---|---|
| PR-AUC | 0,2790 (CI95 0,213–0,379) |
| lift | 5,06× |
| ROC-AUC | 0,8424 |
| precision / recall / F1 | 0,261 / 0,663 / 0,375 |
| TP / FP / FN / TN | 69 / 195 / 35 / 1589 |
| cost | 545 |
| threshold | 0,477 |

Pembanding pada target yang sama: 'selalu alarm' cost 1784, 'tak pernah alarm' cost 1040,
wear rule cost 576.

---

## 7. Interpretasi

**W=10 satu-satunya konfigurasi yang benar-benar berhasil.** Cost 545 mengalahkan wear rule
(576) dan jauh di bawah "selalu alarm" (1784) — hemat 69%. Di semua W lain, wear rule satu
parameter menang. Ini pertama kalinya model ML membenarkan keberadaannya dalam seluruh
rangkaian eksperimen. Perlu dicatat selisih ke wear rule cuma 31 dari 545 (5,7%), jadi
keunggulannya tipis, bukan telak.

**Semakin panjang horizon, semakin model berubah jadi "selalu alarm".** Lihat kolom recall:
0,663 di W=10 lalu 1,000 di W=30/45/60. Di W≥30 model tidak melewatkan satu failure pun
karena ia alarm di hampir setiap baris — di W=60 cost-nya persis sama dengan "selalu alarm"
(1333 = 1333). Itu bukan prediksi, itu menyerah.

**PR-AUC naik tapi lift turun seiring W membesar.** Bukan kontradiksi: prevalence ikut naik
(5,5% → 29,4%), jadi lantai pembandingnya naik lebih cepat dari skornya. Membaca PR-AUC
tanpa prevalence akan menyesatkan — W=60 terlihat terbaik (0,501) padahal justru paling
tidak berguna.

**Precision rendah / recall tinggi itu pilihan, bukan cacat.** Threshold dipilih untuk
meminimalkan 10×FN+FP. Kalau F1 yang dikejar, threshold naik dan F1 melompat 0,276 → 0,449
(pada W=30), tapi 172 dari 292 failure jadi terlewat dan cost naik ke 1842. F1 memberi bobot
sama pada precision dan recall — asumsi yang salah untuk predictive maintenance.

**Accuracy tidak dipakai sama sekali.** Pada W=10, model yang selalu menjawab "aman"
mendapat accuracy 0,945 dan menangkap nol failure. Angka itu tidak mengukur apapun di sini.

**Angka bergeser antar run karena seleksi ada di dalam noise.** Versi script (`sweep_W.py`)
memberi cost 561 dengan 5 feature; versi notebook memberi 545 dengan 4 feature. Keduanya
memakai protokol sama — bedanya hanya aturan parsimoni. Selisih sebesar itu wajar mengingat
sd between-fold ~1,0 pada skala lift. Jangan perlakukan digit terakhir sebagai presisi.

**Rasio biaya 10:1 adalah asumsi, bukan hasil ukur.** Angka itu diwarisi dari notebook lama.
Kalau di pabrik Anda downtime hanya 3× lebih mahal dari inspeksi, seluruh peringkat di tabel
6d bisa berubah dan W=10 belum tentu tetap menang.

---

## 8. Limitations

1. **Sinyalnya memang tipis.** Torque dan rpm white noise (autocorrelation ~0,00), jadi
   failure yang digerakkan keduanya tidak punya prekursor apapun di riwayat sensor. Ini
   plafon struktural data, bukan kelemahan model.
2. **Feature engineering tidak terbukti membantu.** Tujuh feature turunan diuji, semuanya
   ditolak ablation. Selisih antar feature group lebih kecil dari variasi between-fold.
3. **Test set kecil** (1888 baris, 24 cycle) sehingga CI bootstrap lebar. Selisih PR-AUC
   yang lebih kecil dari lebar CI bukan bukti.
4. **Prevalence bergeser antar periode** — di dev 26,4%, di test 14,3%, dan salah satu fold
   validasi mencapai 79,7%. Threshold yang dikunci dari satu periode perlu dikalibrasi ulang
   berkala di produksi.
5. **W=10 dipilih dari sweep, bukan dari kebutuhan operasional.** Kalau persiapan tool
   replacement butuh lebih dari 10 menit, model ini tidak memberi cukup waktu dan angka di
   bagian 6d harus dibaca ulang pada W yang sesuai.
6. **Timestamp bersifat sintetis.** Direkonstruksi dari selisih tool wear, jam mulai dipilih
   bebas (2024-01-01 06:00). Struktur intervalnya benar, tapi jam absolutnya tidak bermakna.
7. **Dataset synthetic.** Label AI4I dihasilkan empat pertidaksamaan deterministik. Angka di
   sini tidak dapat diklaim berlaku pada mesin nyata.
