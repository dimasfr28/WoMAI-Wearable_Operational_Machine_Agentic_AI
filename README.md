# Predictive Maintenance Copilot

Aplikasi predictive maintenance untuk mesin CNC (Haas) yang menggabungkan **prediksi kegagalan mesin berbasis Machine Learning**, **penjelasan model (SHAP)**, **rekomendasi berbasis kemiripan kasus (KNN)**, dan **analisis akar masalah otomatis (RAG/CRAG dengan LLM)** — lengkap dengan estimasi harga spare part dari marketplace. Sistem membaca data sensor mesin, memprediksi risiko kegagalan, menjelaskan *mengapa* (kartu **Early Warning**), menyarankan penyesuaian parameter, mencari SOP penanganan dari manual servis (atau pencarian web sebagai fallback), menghasilkan laporan akhir berbahasa Indonesia secara otomatis, dan menyediakan **chatbot** untuk bertanya soal prediksi/laporan/SOP maupun menjalankan simulasi **"bagaimana jika"** (what-if) terhadap kondisi mesin.

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
| Frontend | Next.js 16 (App Router, TypeScript), Tailwind CSS v4, shadcn/ui (base-ui), Bun — pola BFF (backend dipanggil hanya lewat Server Actions/Route Handlers, browser tidak pernah memanggil backend langsung) |
| Backend | FastAPI (Python), SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 (data relasional) + ChromaDB (vector store) |
| ML | scikit-learn (RandomForest), SHAP, KNN (NearestNeighbors) |
| RAG / LLM | LangChain + LangGraph (Corrective RAG), Groq (LLM inference), sentence-transformers (embedding multilingual) |
| Parsing dokumen | MinerU (PDF → Markdown, OCR/layout, CPU-only, vendored di `backend/vendor/`) |
| Pencarian web | SearXNG (self-hosted metasearch) |
| Harga part | Scraping Alibaba langsung via Playwright (Chromium) di dalam proses backend — **bukan** lagi lewat Firecrawl (dihapus total, lihat catatan di bawah) |
| Auth | JWT (python-jose) + bcrypt (passlib), role-based access control; sesi frontend disimpan sebagai cookie httpOnly |
| Orkestrasi | Docker Compose (`compose.yaml` base + `dev.compose.yaml`/`prod.compose.yaml` override) |

> **Catatan migrasi Firecrawl → Playwright:** endpoint pencarian Alibaba duduk di belakang Akamai Bot Manager yang mem-fingerprint TLS/JA3, bukan cuma header HTTP, sehingga client HTTP biasa (termasuk Firecrawl) selalu terblokir cepat atau lambat. Solusinya: Playwright menjalankan Chromium sungguhan langsung di proses backend (`app/rag/part_price_search.py`), tanpa service terpisah. Saat ini **hanya Alibaba** yang di-scrape langsung dengan cara ini; sumber lain (Shopee/Tokopedia/Lazada) dicari lewat SearXNG.

## Struktur Proyek

```
comfest-18/
├── backend/                    # FastAPI app
│   ├── app/
│   │   ├── api/                  # Route handlers: auth, machine, sensor, knowledgebase, report, sop, chat
│   │   ├── db/                    # SQLAlchemy models, session, migrasi Alembic (11 migrasi)
│   │   ├── ingestion/             # Parsing PDF, chunking, deduplikasi, embedding
│   │   ├── llm/                    # Klien Groq (chat/chat_json)
│   │   ├── ml/                     # Prediktor failure, SHAP, KNN
│   │   ├── rag/                    # Corrective RAG graph, retriever, grader, final_report (LLM), part_price_search (Playwright)
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── vectorstore/            # Klien ChromaDB
│   │   ├── config.py               # Konfigurasi (env vars)
│   │   └── main.py                 # Entry point FastAPI
│   ├── saved/                      # Model ML terlatih (best_model.pkl + performance log)
│   ├── seed_data/                   # Dataset historis untuk seeding awal
│   ├── vendor/                       # MinerU (vendored, dipanggil sbg subprocess/import lokal)
│   ├── scripts/                       # Script migrasi/seeding one-off
│   └── Dockerfile.dev / Dockerfile.prod
├── frontend/                    # Next.js App Router
│   └── src/
│       ├── app/
│       │   ├── (app)/               # Halaman berautentikasi: chat, chat/[id], mesin, sop, riwayat, report
│       │   ├── actions/              # Server Actions — satu-satunya jalur ke backend FastAPI
│       │   ├── api/chat/route.ts     # Route handler yang mem-proxy SSE dari POST /chat backend
│       │   ├── login/, register/     # Auth pages
│       │   └── page.tsx              # Landing page (marketing)
│       ├── components/                # UI (shadcn/ui) + komponen chat (prediction/shap/action-plan/dst.)
│       ├── hooks/, lib/                # Hooks, tipe, util, sesi auth (cookie), penyimpanan riwayat chat (localStorage)
│       └── middleware.ts               # Cek keberadaan cookie sesi (bukan validasinya)
├── searxng/                    # Konfigurasi SearXNG
├── compose.yaml                # Service dasar: postgres, chromadb, searxng
├── dev.compose.yaml             # Override dev: backend+frontend hot-reload, port host
├── prod.compose.yaml            # Override prod: build image, Traefik/Dokploy routing
└── up.sh                        # Wrapper `docker compose up` dengan health-check banner
```

## Alur Kerja Utama (Pipeline Report)

Ketika sebuah **sensor reading** masuk (`POST /sensor/readings`), backend secara sinkron menjalankan pipeline penuh berikut sebelum merespons — tidak ada job queue asinkron:

1. **Assign run** — reading dikelompokkan ke sebuah "run" per mesin (berdasarkan `tool_wear_min` yang naik monoton; turun = run baru dimulai).
2. **Prediksi ML** — 4 fitur mentah sensor diubah jadi 11 fitur (termasuk fitur turunan & risk flag), lalu diprediksi oleh model RandomForest (`predict_failure`) memakai `optimal_threshold` hasil tuning (bukan 0.5).
3. **SHAP** — menjelaskan kontribusi tiap fitur terhadap probabilitas kegagalan.
4. **KNN** — mencari kasus historis termirip (gagal & tidak gagal) serta menghitung "worst-case delta" (penyesuaian parameter menuju titik aman terdekat).
5. **Narasi Early Warning** — LLM menulis penjelasan singkat ("AI Diagnosis") + alasan/dampak dari rekomendasi penyesuaian ("Recommended Action"); angka rekomendasi (fitur, nilai saat ini, nilai target) dihitung deterministik di Python dari hasil worst-case delta, LLM hanya menulis prosanya. Berjalan untuk **setiap** hasil, baik gagal maupun normal.
6. **CRAG (Corrective RAG)** — *hanya jika diprediksi gagal*: query dibangun dari interpretasi SHAP, dokumen manual servis di-retrieve dari ChromaDB, di-grade relevansinya oleh LLM (Groq); jika tidak relevan, fallback ke pencarian web (SearXNG). LLM lalu menyusun jawaban 3 bagian (Apa Masalahnya / SOP Penanganan / Part Bermasalah).
7. **Pencarian harga part** — jika CRAG menyebut nama part, dicari harga & link produk dari marketplace via SearXNG (semua sumber) + Playwright langsung ke Alibaba.
8. **Laporan akhir** — LLM menyusun ringkasan markdown berbahasa Indonesia dari seluruh hasil di atas.

Seluruh hasil pipeline disimpan ke database. `GET /report/latest` **tidak** menghitung ulang apa pun — murni membaca hasil yang sudah tersimpan, sehingga cepat dan idempoten terhadap pemanggilan berulang dari frontend.

**Chatbot (`POST /chat`)** memakai router intent sederhana (satu panggilan LLM mengekstrak intent + parameter dari pesan user, bukan native tool-calling) dan mem-*bypass* pipeline di atas untuk kasus tertentu:
- `predict` — user menyebutkan nilai sensor baru → dijalankan sungguhan lewat pipeline di atas (data tersimpan).
- `latest_report` — membaca `GET /report/latest` yang sudah ada.
- `sop_lookup` — mencocokkan SOP paling relevan dari knowledge base.
- `what_if` — simulasi hipotetis: nilai sensor yang tidak disebut user memakai pembacaan sungguhan terakhir mesin itu sebagai baseline, prediksi + SHAP dijalankan **murni in-memory** (tidak ada baris `sensor_readings`/`sensor_runs`/`predictions` yang ditulis), lalu LLM membandingkan hasil hipotetis terhadap prediksi nyata terakhir mesin tersebut.
- `chitchat` — jawaban umum.

## Menjalankan Aplikasi

Semuanya jalan lewat Docker Compose; tidak ada cara resmi menjalankan backend/frontend di luar container (backend butuh lib sistem seperti `libgl1` untuk OpenCV/MinerU, dan wheel torch CPU-only).

```bash
cp .env.example .env   # isi nilai sungguhan — lihat tabel Environment Variables

./up.sh          # dev, foreground, cetak banner setelah semua service sehat
./up.sh -d        # sama, detached
docker compose -f compose.yaml -f dev.compose.yaml down

# Backend & frontend hot-reload dari source saat dev (uvicorn --reload, bun run dev)
# — tidak perlu restart setelah edit backend/app/ atau frontend/src/.

# Produksi (Dokploy/Traefik) — butuh network eksternal `dokploy-network` dan
# BACKEND_DOMAIN/FRONTEND_DOMAIN terisi di .env:
docker compose -f compose.yaml -f prod.compose.yaml up -d --build
```

Setelah semua service sehat:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8002` (Swagger UI di `/docs`)
- ChromaDB: `http://localhost:8001`
- SearXNG: `http://localhost:8080`
- PostgreSQL: host port `5434` (bukan `5432` — port native/container lain di mesin dev sudah memakainya; port di dalam container tetap `5432`)

Migrasi database (Alembic) dijalankan otomatis setiap kali container backend start (`alembic upgrade head`).

> ⚠️ Frontend memakai cookie sesi `secure: true` di production (praktik Next.js yang benar) — artinya login hanya berfungsi lewat `http://localhost:3000` dari mesin yang sama. Mengakses lewat IP LAN/hostname via HTTP polos akan membuat cookie diam-diam gagal tersimpan sampai TLS dipasang di depan aplikasi.

### Environment Variables (`.env`)

Lihat `.env.example` untuk daftar lengkap dengan nilai default/contoh. Ringkasannya:

| Variabel | Keterangan |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` | Koneksi PostgreSQL utama |
| `CHROMA_HOST`, `CHROMA_PORT`, `CHROMA_COLLECTION_DOCS`, `CHROMA_COLLECTION_SENSOR` | Koneksi & nama collection ChromaDB (dua collection terpisah: dokumen & auto-chunk sensor run) |
| `EMBEDDING_MODEL` | Model sentence-transformers untuk embedding (default: multilingual MiniLM) |
| `GROQ_API_KEY`, `GROQ_MODEL` | Kredensial & model LLM Groq (dipakai CRAG, laporan akhir, narasi Early Warning, dan chatbot) |
| `ML_MODEL_PATH`, `ML_PERFORMANCE_LOG_PATH` | Path model ML terlatih & log performa |
| `PDF_LIBRARY_DIR` | Direktori penyimpanan file PDF ter-upload di dalam container |
| `SEARXNG_BASE_URL` | URL instance SearXNG |
| `DUPLICATE_CHUNK_SIMILARITY_THRESHOLD`, `DUPLICATE_CHUNK_RATIO_THRESHOLD` | Ambang batas deteksi dokumen duplikat |
| `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `JWT_ALGORITHM` | Konfigurasi token autentikasi |
| `BACKEND_DOMAIN`, `FRONTEND_DOMAIN` | Hanya dipakai di production (routing Traefik/Dokploy), tidak dipakai di dev |

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
| PATCH | `/machines/{machine_id}` | role ≥ `engineer` | Ubah data mesin |
| DELETE | `/machines/{machine_id}` | role ≥ `engineer` | Hapus mesin |
| GET | `/machines/{machine_id}/status` | user login | Ringkasan status operasional + panel Early Warning per-parameter (SHAP + worst-case delta). **Endpoint backend ini sudah lengkap tapi saat ini tidak dipanggil frontend mana pun** — halaman dashboard lama yang mengonsumsinya dihapus saat migrasi ke Next.js (lihat [Status Pengerjaan](#status-pengerjaan)) |

### Sensor (`/sensor`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| POST | `/sensor/readings?machine_id=` | - | Kirim satu pembacaan sensor `{timestamp?, air_temperature_k, process_temperature_k, rotational_speed_rpm, tool_wear_min}`. Memicu prediksi ML + seluruh pipeline report secara sinkron |
| POST | `/sensor/readings/batch?machine_id=` | - | Kirim banyak reading sekaligus (disiapkan untuk integrasi Airflow/DAG di masa depan; **belum ada pemanggil apa pun**, termasuk frontend) |
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

> Backend endpoint ini lengkap dan aktif dipakai pipeline report (retrieval CRAG), tapi **tidak ada halaman frontend** untuk mengelola knowledgebase (upload/lihat/hapus dokumen) di UI Next.js saat ini — lihat [Status Pengerjaan](#status-pengerjaan).

### SOP (`/sops`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| GET | `/sops` | - | Daftar seluruh SOP (global, tidak terikat mesin atau failure-mode tertentu — dicocokkan lewat LLM berdasarkan gejala) |
| POST | `/sops` | role ≥ `engineer` | Tambah SOP baru. Body: `{title, symptoms, body, steps, reference}` |
| PATCH | `/sops/{sop_id}` | role ≥ `engineer` | Ubah SOP |
| DELETE | `/sops/{sop_id}` | role ≥ `engineer` | Hapus SOP |

### Chat (`/chat`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| POST | `/chat` | user login | Endpoint agent chatbot, balasan **SSE** (`text/event-stream`). Body: `{session_id, message}`. Router intent (`predict`/`latest_report`/`sop_lookup`/`what_if`/`chitchat`) diklasifikasi lewat satu panggilan LLM, lalu di-dispatch ke handler yang sesuai. Riwayat pesan disimpan server-side ke `chat_sessions`/`chat_messages`, **tapi daftar riwayat yang tampil di frontend (`/riwayat`) saat ini dibaca dari localStorage browser, bukan dari tabel ini** — lihat [Status Pengerjaan](#status-pengerjaan) |

### Report (`/report`)

| Method | Path | Auth | Deskripsi |
|---|---|---|---|
| GET | `/report/latest?machine_id=` | - | Laporan lengkap terbaru: snapshot sensor, prediksi (label, probabilitas, health score), SHAP, rekomendasi KNN, AI Diagnosis + Recommended Action (Early Warning), root cause analysis (RAG), harga part, teks laporan akhir dari LLM |
| GET | `/report/history?machine_id=&limit=50` | - | Riwayat prediksi (ringkas: label, probabilitas, waktu) |

> Sebagian besar endpoint GET yang bersifat baca-saja (dokumen/chunk, runs, history sensor, report, sop) **tidak menegakkan autentikasi** di level kode meskipun frontend selalu mengirim token — hanya endpoint yang mengubah data, bersifat admin, atau di bawah `/machines` (termasuk `GET`-nya) yang diproteksi `require_role`/`get_current_user`. Perlu ditinjau kembali secara konsisten sebelum production jika seluruh data ini dianggap sensitif.

## Skema Database Inti

- **`users`** — akun & role (`admin`/`engineer`/`viewer`)
- **`machines`** — mesin yang dimonitor (multi-mesin per akun); `status` masih nilai statis (lihat [Status Pengerjaan](#status-pengerjaan))
- **`documents` / `document_chunks`** — dokumen knowledgebase (PDF manual servis, atau chunk otomatis dari sensor run) & potongan teksnya (juga di-embed ke ChromaDB)
- **`sensor_runs` / `sensor_readings`** — sesi kerja mesin & pembacaan sensor per waktu
- **`predictions`** — hasil prediksi ML per reading
- **`shap_explanations`** — kontribusi tiap fitur (SHAP) per prediksi
- **`recommendations`** — hasil KNN (kasus mirip gagal/tidak gagal, worst-case delta)
- **`root_cause_analyses`** — query, jawaban, dan sumber (RAG/web fallback) dari CRAG
- **`part_price_lookups`** — hasil pencarian harga part dari marketplace
- **`sops`** — knowledge base SOP mandiri (global, dicocokkan lewat LLM berdasarkan gejala/query)
- **`final_reports`** — teks laporan akhir dari LLM, plus `ai_explanation`/`recommended_action` (narasi & rekomendasi kartu Early Warning), digenerate sekali bersamaan dengan `report_text`
- **`chat_sessions` / `chat_messages`** — riwayat percakapan chatbot, **diisi aktif** oleh `POST /chat` (lihat catatan soal frontend `/riwayat` di [Dokumentasi API](#chat-chat))
- **`agent_tool_logs`** — skema sudah disiapkan lewat migrasi awal, **belum ada kode yang menulis ke tabel ini**

Migrasi dikelola dengan Alembic (`backend/app/db/migrations/versions/`), 11 migrasi: skema awal → SHAP base value → seed dataset sensor chunks → multi-machine support → SOP library → narasi Early Warning, dst.

## Model Machine Learning

- **Task**: klasifikasi biner — apakah mesin CNC akan mengalami *failure* atau tidak.
- **Algoritma**: RandomForest (scikit-learn), dipilih dari proses eksperimen (disimpan di `backend/saved/best_performance_log.json`).
- **Fitur**: 4 fitur mentah dari sensor (`air_temperature_k`, `process_temperature_k`, `rotational_speed_rpm`, `tool_wear_min`) + 7 fitur turunan (selisih/rasio suhu, laju keausan tool, interaksi rpm×wear, dan dua *risk flag* berbasis IQR bound data training) = 11 fitur total.
- **Threshold keputusan**: bukan 0.5 baku, melainkan `optimal_threshold` (≈0.503) hasil tuning yang tersimpan di log performa.
- **Penanganan imbalance**: class weight `{0: 1, 1: 12}` (kelas gagal jauh lebih jarang).
- **Explainability**: SHAP `TreeExplainer` per prediksi, ditampilkan untuk 4 fitur mentah yang mudah dipahami pengguna.
- **Rekomendasi**: `NearestNeighbors` (KNN) mencari kasus historis termirip dan titik aman terdekat ("worst-case delta") untuk menyarankan penyesuaian parameter operasional — dipakai juga untuk menghitung angka kartu Recommended Action dan simulasi what-if.

## Status Pengerjaan

### ✅ Sudah selesai

- Autentikasi & manajemen user berbasis JWT dengan role hierarkis (admin/engineer/viewer); sesi frontend lewat cookie httpOnly
- Manajemen multi-mesin (CRUD, tersimpan penuh di database — bukan lagi data dummy)
- Ingest data sensor (manual & batch), pengelompokan otomatis menjadi "run" per sesi kerja
- Prediksi kegagalan mesin (ML RandomForest) dengan feature engineering penuh & threshold hasil tuning
- Penjelasan prediksi dengan SHAP + rekomendasi berbasis KNN (kasus mirip + worst-case delta)
- Kartu **Early Warning** di halaman Laporan: banner risiko, kondisi sensor terkini, AI Diagnosis (penjelasan LLM), dan Recommended Action (angka deterministik + prosa LLM)
- Knowledgebase dokumen (backend penuh): upload PDF, parsing otomatis (MinerU, OCR/layout), deteksi duplikat (hash + semantik), chunking, embedding ke ChromaDB, penghapusan dokumen
- Auto-generate chunk knowledgebase dari data sensor (setiap run mesin yang selesai)
- Corrective RAG (CRAG) untuk analisis akar masalah: retrieval dari knowledgebase → grading relevansi via LLM → fallback pencarian web (SearXNG) bila tidak relevan
- Pencarian estimasi harga part dari marketplace (SearXNG + scraping Alibaba langsung via Playwright)
- Generasi laporan akhir otomatis berbahasa Indonesia (Groq LLM)
- **Chatbot AI** (`POST /chat`, SSE): router intent (predict/latest_report/sop_lookup/what_if/chitchat), termasuk **simulasi what-if** yang membandingkan skenario hipotetis terhadap kondisi mesin nyata terakhir tanpa menulis data sungguhan
- Manajemen SOP mandiri (CRUD lewat backend, tersimpan di database, dicocokkan otomatis via LLM berdasarkan gejala)
- Frontend Next.js (App Router): landing page, Login/Register, Chat (+ riwayat sesi per percakapan), Mesin (CRUD), SOP (CRUD), Riwayat percakapan, Laporan (Early Warning + detail SHAP/KNN/Root Cause/Harga Part/Laporan Akhir)
- Orkestrasi penuh via Docker Compose (Postgres, ChromaDB, SearXNG, backend, frontend), dengan override terpisah untuk dev dan prod (Dokploy/Traefik)

### 🚧 Belum dikerjakan / diketahui sebagai gap

- **Halaman knowledgebase di frontend** belum ada — upload/lihat/hapus dokumen PDF hanya bisa lewat API langsung (`/docs`) meski backend-nya sudah lengkap dan aktif dipakai pipeline.
- **Riwayat chat di frontend tidak membaca dari database** — halaman `/riwayat` memakai `localStorage` browser (`frontend/src/lib/storage.ts`), padahal backend sudah aktif menyimpan tiap sesi/pesan ke `chat_sessions`/`chat_messages`. Dua sumber kebenaran ini belum disatukan.
- **`GET /machines/{id}/status`** (panel Early Warning per-parameter di level mesin) sudah lengkap di backend tapi **tidak dipanggil frontend mana pun** — peninggalan desain dashboard lama yang sengaja dihapus saat migrasi ke Next.js (dashboard analitik penuh di luar scope MVP kompetisi).
- Integrasi **DAG/Airflow** untuk input sensor otomatis terjadwal — endpoint `POST /sensor/readings/batch` sudah disiapkan tapi belum ada pemanggil DAG yang nyata. **Rencana ke depan:** input sensor sungguhan akan datang dari perangkat **ESP32** yang memanggil `POST /sensor/readings` langsung — endpoint ini sudah cukup, tidak perlu arsitektur baru; fitur simulasi (what-if, dsb.) harus tetap terpisah dari jalur data sungguhan ini.
- Penegakan autentikasi yang belum konsisten di seluruh endpoint GET — sebagian besar endpoint baca (dokumen, chunk, sensor history/runs, report, SOP) masih bersifat publik meski frontend selalu mengirim token; hanya endpoint di bawah `/machines` yang sudah diproteksi penuh termasuk `GET`-nya.
- Status operasional mesin (`machines.status`) masih nilai statis (`"running"` untuk semua mesin) — belum ada feed real-time (rencananya dari ESP32) untuk mengisinya secara dinamis.
- `agent_tool_logs` — skema tabel sudah ada lewat migrasi awal, tapi belum ada kode yang menulisinya (dicadangkan untuk logging tool-call agent yang lebih rinci di masa depan).

---

**Catatan keamanan:** `.env` di root repo berisi kredensial nyata dan **tidak** ikut ter-commit ke git (lihat `.gitignore`). Gunakan `.env.example` sebagai referensi struktur variabel; jangan pernah menaruh nilai asli di file yang ter-track git.
