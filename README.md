# Predictive Maintenance Copilot

Aplikasi predictive maintenance untuk mesin CNC (Haas) yang menggabungkan **prediksi kegagalan mesin berbasis Machine Learning**, **penjelasan model (SHAP)**, **rekomendasi berbasis kemiripan kasus (KNN)**, dan **analisis akar masalah otomatis (RAG/CRAG dengan LLM)** — lengkap dengan estimasi harga spare part dari marketplace. Sistem membaca data sensor mesin, memprediksi risiko kegagalan, menjelaskan *mengapa*, menyarankan penyesuaian parameter, mencari SOP penanganan dari manual servis (atau pencarian web sebagai fallback), dan menghasilkan laporan akhir berbahasa Indonesia secara otomatis.

## Daftar Isi

- [Arsitektur & Tech Stack](#arsitektur--tech-stack)
- [Struktur Proyek](#struktur-proyek)
- [Alur Kerja Utama](#alur-kerja-utama-pipeline-report)
- [Menjalankan Aplikasi](#menjalankan-aplikasi)
- [Dokumentasi API](#dokumentasi-api)
- [Skema Database](#skema-database-inti)
- [Model Machine Learning](#model-machine-learning)
- [Status Pengerjaan](#status-pengerjaan)

## Arsitektur & Tech Stack

| Layer | Teknologi |
|---|---|
| Frontend | React 18 + Vite, React Router, Recharts, disajikan via Nginx |
| Backend | FastAPI (Python 3.11), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 (data relasional) + ChromaDB (vector store) |
| ML | scikit-learn (RandomForest), SHAP, KNN (NearestNeighbors) |
| RAG / LLM | LangChain + LangGraph (Corrective RAG), Groq (LLM inference), sentence-transformers (embedding multilingual) |
| Parsing dokumen | MinerU (PDF → Markdown, OCR/layout, CPU-only) |
| Pencarian web | SearXNG (self-hosted metasearch) |
| Scraping harga part | Firecrawl (self-hosted dari source, folder `firecrawl/`) |
| Auth | JWT (python-jose) + bcrypt (passlib), role-based access control |
| Orkestrasi | Docker Compose |

Frontend berkomunikasi dengan backend murni lewat REST API (JSON), dengan JWT Bearer token untuk endpoint yang butuh autentikasi.

## Struktur Proyek

```
app/
├── backend/                 # FastAPI app
│   ├── app/
│   │   ├── api/              # Route handlers (auth, machine, sensor, knowledgebase, report)
│   │   ├── db/                # SQLAlchemy models, session, migrasi Alembic
│   │   ├── ingestion/         # Parsing PDF, chunking, deduplikasi, embedding
│   │   ├── llm/                # Klien Groq
│   │   ├── ml/                 # Prediktor failure, SHAP, KNN
│   │   ├── rag/                # Corrective RAG graph, retriever, pencarian harga part
│   │   ├── schemas/            # Pydantic request/response models
│   │   ├── vectorstore/        # Klien ChromaDB
│   │   ├── config.py           # Konfigurasi (env vars)
│   │   └── main.py             # Entry point FastAPI
│   ├── saved/                  # Model ML terlatih (best_model.pkl + performance log)
│   ├── seed_data/               # Dataset historis untuk seeding awal
│   ├── scripts/                  # Script migrasi/seeding one-off
│   └── Dockerfile
├── frontend/                 # React SPA
│   └── src/
│       ├── api/client.js       # Klien HTTP ke backend
│       ├── components/          # MachineContext (state mesin terpilih)
│       └── pages/                # Login, MachineSelect, Dashboard, Knowledgebase, Report
├── firecrawl/                # Proyek open-source Firecrawl (vendored dari upstream, self-hosted)
├── searxng/                  # Konfigurasi SearXNG
├── docker-compose.yml        # Orkestrasi seluruh service
└── up.sh                     # Wrapper untuk `docker compose up` dengan health-check banner
```

> **Catatan:** folder `firecrawl/` adalah proyek open-source pihak ketiga (github.com/mendableai/firecrawl) yang di-*vendor* utuh ke repo ini karena image resminya tidak tersedia di Docker Hub — dijalankan sebagai service Docker terpisah (`firecrawl-api`, dst.) dan hanya diakses backend lewat HTTP (`POST /v1/scrape`), bukan diimpor sebagai kode Python.

## Alur Kerja Utama (Pipeline Report)

Ketika sebuah **sensor reading** masuk (`POST /sensor/readings`), backend secara sinkron menjalankan pipeline penuh berikut sebelum merespons:

1. **Assign run** — reading dikelompokkan ke sebuah "run" per mesin (berdasarkan `tool_wear_min` yang naik monoton; turun = run baru dimulai).
2. **Prediksi ML** — 4 fitur mentah sensor diubah jadi 11 fitur (termasuk fitur turunan & risk flag), lalu diprediksi oleh model RandomForest (`predict_failure`).
3. **SHAP** — menjelaskan kontribusi tiap fitur terhadap probabilitas kegagalan.
4. **KNN** — mencari kasus historis termirip (gagal & tidak gagal) serta menghitung "worst-case delta" (penyesuaian parameter menuju titik aman terdekat).
5. **CRAG (Corrective RAG)** — *hanya jika diprediksi gagal*: query dibangun dari interpretasi SHAP, dokumen manual servis di-retrieve dari ChromaDB, di-grade relevansinya oleh LLM (Groq); jika tidak relevan, fallback ke pencarian web (SearXNG). LLM lalu menyusun jawaban 3 bagian (Apa Masalahnya / SOP Penanganan / Part Bermasalah).
6. **Pencarian harga part** — jika CRAG menyebut nama part, dicari harga & link produk dari marketplace (Shopee, Tokopedia, Lazada, Alibaba, dll.) via Firecrawl + SearXNG.
7. **Laporan akhir** — LLM menyusun ringkasan markdown berbahasa Indonesia dari seluruh hasil di atas.

Seluruh hasil pipeline disimpan ke database. Endpoint `GET /report/latest` **tidak** menghitung ulang apa pun — murni membaca hasil yang sudah tersimpan, sehingga cepat dan idempoten terhadap pemanggilan berulang dari frontend.

## Menjalankan Aplikasi

```bash
# Konfigurasi environment variables terlebih dahulu (lihat bagian Environment Variables)
cp .env.example .env   # jika tersedia, sesuaikan nilainya

./up.sh          # jalankan semua service (foreground)
./up.sh -d        # jalankan di background (detached)
```

Setelah semua service sehat:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8002` (docs interaktif di `http://localhost:8002/docs`)
- ChromaDB: `http://localhost:8001`
- SearXNG: `http://localhost:8080`
- Firecrawl API: `http://localhost:3002`

Migrasi database (Alembic) dijalankan otomatis setiap kali container backend start.

### Environment Variables (`.env`)

| Variabel | Keterangan |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | Koneksi PostgreSQL utama |
| `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION_DOCS`, `CHROMA_COLLECTION_SENSOR` | Koneksi & nama collection ChromaDB |
| `EMBEDDING_MODEL` | Model sentence-transformers untuk embedding (default: multilingual MiniLM) |
| `GROQ_API_KEY`, `GROQ_MODEL` | Kredensial & model LLM Groq |
| `ML_MODEL_PATH`, `ML_PERFORMANCE_LOG_PATH` | Path model ML terlatih & log performa |
| `SEARXNG_BASE_URL` | URL instance SearXNG |
| `FIRECRAWL_API_URL`, `FIRECRAWL_API_KEY` | Koneksi ke service Firecrawl |
| `ALIBABA_COOKIES` | Cookie sesi login Alibaba (JSON) untuk melewati proteksi anti-bot saat scraping harga |
| `DUPLICATE_CHUNK_SIMILARITY_THRESHOLD`, `DUPLICATE_CHUNK_RATIO_THRESHOLD` | Ambang batas deteksi dokumen duplikat |
| `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `JWT_ALGORITHM` | Konfigurasi token autentikasi |

> ⚠️ Beberapa variabel (`SUPABASE_*`) ada di `.env` tapi **tidak digunakan** oleh kode aplikasi manapun (kemungkinan sisa konfigurasi yang belum dibersihkan).

## Dokumentasi API

Base URL (dev, via Docker Compose): `http://localhost:8002`. Dokumentasi interaktif otomatis (Swagger UI) tersedia di `/docs` dan `/redoc`.

Autentikasi memakai **JWT Bearer token** (`Authorization: Bearer <token>`) yang didapat dari `POST /auth/login`. Role tersedia: `viewer` < `engineer` < `admin` (hierarkis — role lebih tinggi otomatis memenuhi syarat role lebih rendah).

### Health Check

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| GET | `/health` | - | Cek status service, balasan `{"status": "ok"}` |

### Auth (`/auth`, `/users`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| POST | `/auth/register` | Terbuka **hanya** saat tabel `users` masih kosong (bootstrap admin pertama); setelah itu 403 dan mengarahkan ke `/auth/register/admin` | Registrasi user baru. Body: `{username, email, password, full_name?, role}` |
| POST | `/auth/register/admin` | role ≥ `admin` | Registrasi user baru oleh admin (jalur eksplisit setelah bootstrap) |
| POST | `/auth/login` | - | Login. Body: `{username, password}` → balasan `{access_token, token_type}` |
| GET | `/users` | role ≥ `admin` | Daftar seluruh user |
| PATCH | `/users/{user_id}/role` | role ≥ `admin` | Ubah role seorang user. Body: `{role}` |

### Machines (`/machines`)

Setiap mesin memiliki data sensor, dokumen, dan laporan sendiri — hampir semua endpoint domain lain butuh `machine_id`.

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| GET | `/machines` | user login | Daftar semua mesin (+ jumlah dokumen & run) |
| POST | `/machines` | role ≥ `engineer` | Tambah mesin baru. Body: `{name, machine_type?}` |
| GET | `/machines/{machine_id}` | user login | Detail satu mesin |
| GET | `/machines/{machine_id}/status` | user login | Ringkasan dashboard: status operasional (RUNNING/WARNING/IDLE/OFFLINE), waktu reading terakhir, stabilitas prediksi (%), dan panel **AI Early Warning** (kombinasi SHAP + KNN) |

### Sensor (`/sensor`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| POST | `/sensor/readings?machine_id=` | opsional | Kirim satu pembacaan sensor `{timestamp?, air_temperature_k, process_temperature_k, rotational_speed_rpm, tool_wear_min}`. Memicu prediksi ML + seluruh pipeline report secara sinkron |
| POST | `/sensor/readings/batch?machine_id=` | - | Kirim banyak reading sekaligus (disiapkan untuk integrasi Airflow/DAG di masa depan, belum dipakai frontend) |
| GET | `/sensor/runs?machine_id=` | - | Daftar seluruh "run" mesin (sesi kerja, dikelompokkan otomatis dari tool wear) |
| GET | `/sensor/readings/history?machine_id=` | - | Time-series 4 parameter sensor untuk run terbaru + statistik min/max/avg/current + flag anomali (berbasis IQR) |

### Knowledgebase (`/knowledgebase`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| GET | `/knowledgebase/documents?machine_id=` | - | Daftar dokumen milik satu mesin |
| GET | `/knowledgebase/upload/check-filename?filename=&machine_id=` | user login | Cek apakah nama file sudah ada (untuk konfirmasi replace di UI) |
| POST | `/knowledgebase/upload/pdf?machine_id=&replace=` | role ≥ `engineer` | Upload PDF (`multipart/form-data`). Pipeline: parsing (MinerU) → cek duplikat (hash + semantik) → chunking → embedding → simpan ke Postgres + Chroma |
| GET | `/knowledgebase/documents/{document_id}/chunks` | - | Daftar chunk teks dari satu dokumen |
| DELETE | `/knowledgebase/documents/{document_id}` | role ≥ `engineer` | Hapus dokumen (Postgres + Chroma + file fisik) |

### Report (`/report`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| GET | `/report/latest?machine_id=` | - | Laporan lengkap terbaru: snapshot sensor, prediksi (label, probabilitas, health score), SHAP, rekomendasi KNN, root cause analysis (RAG), harga part, teks laporan akhir dari LLM |
| GET | `/report/history?machine_id=&limit=50` | - | Riwayat prediksi (ringkas: label, probabilitas, waktu) |

> Endpoint GET yang bersifat baca-saja (list dokumen, chunk, runs, history, report) saat ini **tidak menegakkan autentikasi** di level kode meskipun frontend selalu mengirim token — hanya endpoint yang mengubah data atau bersifat admin yang diproteksi `require_role`/`get_current_user`. Perlu ditinjau kembali sebelum production jika data ini dianggap sensitif.

## Skema Database Inti

- **`users`** — akun & role (`admin`/`engineer`/`viewer`)
- **`machines`** — mesin yang dimonitor (multi-mesin per akun)
- **`documents` / `document_chunks`** — dokumen knowledgebase (PDF manual servis, atau chunk otomatis dari sensor run) & potongan teksnya (juga di-embed ke ChromaDB)
- **`sensor_runs` / `sensor_readings`** — sesi kerja mesin & pembacaan sensor per waktu
- **`predictions`** — hasil prediksi ML per reading
- **`shap_explanations`** — kontribusi tiap fitur (SHAP) per prediksi
- **`recommendations`** — hasil KNN (kasus mirip gagal/tidak gagal, worst-case delta)
- **`root_cause_analyses`** — query, jawaban, dan sumber (RAG/web fallback) dari CRAG
- **`part_price_lookups`** — hasil pencarian harga part dari marketplace
- **`final_reports`** — teks laporan akhir yang digenerate LLM
- **`chat_sessions` / `chat_messages` / `agent_tool_logs`** — skema **sudah disiapkan** untuk fitur chatbot, tapi **belum diimplementasikan** (lihat [Status Pengerjaan](#status-pengerjaan))

Migrasi dikelola dengan Alembic (`backend/app/db/migrations/versions/`, 9 migrasi: skema awal → multi-machine support → dst).

## Model Machine Learning

- **Task**: klasifikasi biner — apakah mesin CNC akan mengalami *failure* atau tidak.
- **Algoritma**: RandomForest (scikit-learn), dipilih dari proses eksperimen (disimpan di `backend/saved/best_performance_log.json`).
- **Fitur**: 4 fitur mentah dari sensor (`air_temperature_k`, `process_temperature_k`, `rotational_speed_rpm`, `tool_wear_min`) + 7 fitur turunan (selisih/rasio suhu, laju keausan tool, interaksi rpm×wear, dan dua *risk flag* berbasis IQR bound data training) = 11 fitur total.
- **Threshold keputusan**: bukan 0.5 baku, melainkan `optimal_threshold` (≈0.503) hasil tuning yang tersimpan di log performa.
- **Penanganan imbalance**: class weight `{0: 1, 1: 12}` (kelas gagal jauh lebih jarang).
- **Explainability**: SHAP `TreeExplainer` per prediksi, ditampilkan untuk 4 fitur mentah yang mudah dipahami pengguna.
- **Rekomendasi**: `NearestNeighbors` (KNN) mencari kasus historis termirip dan titik aman terdekat ("worst-case delta") untuk menyarankan penyesuaian parameter operasional.

## Status Pengerjaan

### ✅ Sudah selesai

- Autentikasi & manajemen user berbasis JWT dengan role hierarkis (admin/engineer/viewer)
- Manajemen multi-mesin (CRUD dasar, status dashboard per mesin)
- Ingest data sensor (manual & batch), pengelompokan otomatis menjadi "run" per sesi kerja
- Prediksi kegagalan mesin (ML RandomForest) dengan feature engineering penuh & threshold hasil tuning
- Penjelasan prediksi dengan SHAP
- Rekomendasi berbasis KNN (kasus mirip + saran penyesuaian parameter/"worst-case delta")
- Panel **AI Early Warning** di dashboard (kombinasi SHAP + KNN)
- Knowledgebase dokumen: upload PDF, parsing otomatis (MinerU, OCR/layout), deteksi duplikat (hash + semantik), chunking, embedding ke ChromaDB, penghapusan dokumen
- Auto-generate chunk knowledgebase dari data sensor (setiap run mesin yang selesai)
- Corrective RAG (CRAG) untuk analisis akar masalah: retrieval dari knowledgebase → grading relevansi via LLM → fallback pencarian web (SearXNG) bila tidak relevan
- Pencarian estimasi harga part dari marketplace (Shopee/Tokopedia/Lazada/Alibaba/dll via Firecrawl + SearXNG)
- Generasi laporan akhir otomatis berbahasa Indonesia (Groq LLM)
- Frontend React: halaman Login, pemilihan mesin, Dashboard (gauge, grafik sensor, early warning), Knowledgebase (upload/lihat/hapus dokumen), Report (laporan lengkap per prediksi)
- Script seeding data historis & migrasi PDF library yang sudah ada
- Orkestrasi penuh via Docker Compose (Postgres, ChromaDB, SearXNG, Firecrawl self-hosted, backend, frontend)

### 🚧 Belum dikerjakan / direncanakan

- **Chatbot AI**: skema database (`chat_sessions`, `chat_messages`, `agent_tool_logs`) sudah disiapkan lewat migrasi, tapi route backend (`routes_chat.py`) dan halaman frontend (`ChatbotPage.jsx`) **belum diimplementasikan**.
- Integrasi **DAG/Airflow** untuk input sensor otomatis terjadwal — endpoint `POST /sensor/readings/batch` sudah disiapkan tapi belum ada pemanggil DAG yang nyata.
- Penegakan autentikasi yang konsisten di seluruh endpoint GET (saat ini beberapa endpoint baca bersifat publik meski frontend selalu mengirim token).
- Status operasional mesin (`machines.status`) masih nilai statis (`"running"` untuk semua mesin) — belum ada feed real-time dari PLC/OPC-UA untuk mengisinya secara dinamis.
- Pembersihan variabel environment `SUPABASE_*` yang tidak lagi digunakan oleh kode manapun.

---

**Catatan keamanan:** file `.env` di root repo saat ini berisi nilai kredensial nyata (mis. `GROQ_API_KEY`, `ALIBABA_COOKIES`, konfigurasi Supabase) alih-alih hanya berupa contoh/placeholder. Pastikan file ini tidak pernah ikut ter-commit ke git publik, dan pertimbangkan memisahkan nilai asli ke pengelola secret terpisah serta menyediakan `.env.example` berisi placeholder untuk dokumentasi.
