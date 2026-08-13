# Spec Desain — Backend Chat Agent (`/chat`) untuk AIC COMPFEST 18

Tanggal: 2026-08-13
Status: disetujui untuk perencanaan implementasi

## Konteks

comfest-18 adalah submission tim untuk **AI Innovation Challenge (AIC) COMPFEST 18** (deadline penyisihan 25 Agustus 2026, lihat rulebook di `[AIC] AI Innovation Challenge.pdf`). Submission ini berbasis frontend Next.js di branch `ariel` (hasil migrasi dari `wo_m_ai`), bukan frontend React+Vite lama di `dimas`.

Frontend Next.js sudah punya UI chat lengkap (`frontend/src/app/(app)/chat/`) yang mengirim `POST {BACKEND_URL}/chat` dan mengharapkan respons **SSE** dengan kontrak event yang sudah terdefinisi di `frontend/src/app/api/chat/route.ts` — tapi endpoint `/chat` **tidak pernah ada di backend**, jadi setiap interaksi chat saat ini 100% dijawab oleh mock lokal (`frontend/src/lib/mock/scenarios.ts`). Ini fitur inti (core AI interaction) yang paling dinilai rubrik AIC ("Implementasi Teknologi & Kematangan Arsitektur" 25%, "Kesiapan MVP" 15%) — dan saat ini palsu.

Audit codebase juga menemukan celah lain: endpoint sensor (`/sensor/readings`, dst.) dan report (`/report/latest`, dst.) tidak dikonsumsi sama sekali oleh frontend Next.js manapun. Diputuskan bersama user: keduanya akan diekspos lewat chat (bukan halaman dashboard/report terpisah — itu eksplisit dilarang rubrik AIC sebagai "dashboard analitik tingkat lanjut"). Halaman Knowledgebase (upload/list/hapus dokumen) **di luar scope spec ini** — sub-project terpisah setelah `/chat` selesai.

## Keputusan Utama

| Aspek | Keputusan |
|---|---|
| Gaya agent | Router intent sederhana (satu panggilan `chat_json()` mengekstrak intent+parameter), bukan native tool-calling Groq — `groq_client.py` belum dukung `tools=`, dan router lebih deterministik untuk demo langsung dalam waktu terbatas |
| Reuse pipeline | Intent `predict` insert `SensorRun`+`SensorReading` sungguhan lalu panggil langsung `_run_report_pipeline()` yang sama dipakai `POST /sensor/readings` — bukan reimplementasi SHAP/CRAG/report dari nol |
| Streaming teks | Bukan streaming token asli dari Groq (belum didukung `groq_client.py`). Jawaban akhir dihitung penuh secara sinkron, lalu di-chunk kata-per-kata ke event `text` — cukup untuk UX demo, jauh lebih rendah risiko |
| Persistensi chat | `chat_sessions`/`chat_messages` (tabel sudah ada dari migrasi lama, belum pernah dipakai) — ditulis sinkron per giliran, bukan background job |
| Cakupan tool | 3 intent: `predict` (jalankan prediksi dari deskripsi kondisi mesin), `latest_report` (lihat laporan/prediksi terakhir suatu mesin), `sop_lookup` (cari SOP relevan) — plus fallback `chitchat` |
| Halaman Dashboard/Report terpisah | Tidak dibangun — rubrik AIC eksplisit larang "dashboard analitik tingkat lanjut" untuk penyisihan; data prediksi/SHAP/report disajikan sebagai jawaban chat |
| Event `downtime` | Tidak pernah di-emit — backend tidak punya model estimasi biaya/downtime nyata; event ini opsional di kontrak FE jadi aman dihilangkan tanpa mengubah kontrak |
| Perbaikan tipe FE | `PredictionResult` FE (masih pakai taksonomi AI4I `TWF/HDF/PWF/OSF/RNF`) diganti field asli (`label`, `probability`, `healthScore`, `riskLevel` dari threshold baru) — comfest-18 tidak punya taksonomi failure-mode |

## Backend: Endpoint `/chat`

**File baru** `backend/app/api/routes_chat.py`, prefix `/chat`:

```
POST /chat
Body: {"message": str, "session_id": str}
Auth: require login (get_current_user) — chat menulis riwayat per user
Response: text/event-stream (SSE), format `data: {json}\n\n` per event
```

### Alur per request

1. **Resolve/buat `ChatSession`** — kalau `session_id` belum ada row di `chat_sessions` untuk user ini, buat baru (title dari beberapa kata pertama pesan). Simpan `ChatMessage` role=`user` untuk pesan masuk.
2. **Klasifikasi intent** — satu panggilan `chat_json()` dengan prompt terstruktur, mengekstrak JSON:
   ```json
   {
     "intent": "predict" | "latest_report" | "sop_lookup" | "chitchat",
     "machine_id": "string atau null",
     "air_temperature_k": number atau null,
     "process_temperature_k": number atau null,
     "rotational_speed_rpm": number atau null,
     "tool_wear_min": number atau null,
     "sop_query": "string atau null"
   }
   ```
3. **Dispatch berdasar intent:**
   - **`predict`**, ada field sensor yang `null` → emit `needs_input` dengan pertanyaan spesifik field yang hilang (dalam Bahasa Indonesia).
   - **`predict`**, lengkap tapi `machine_id` kosong → emit `needs_input` minta user pilih/sebut nama mesin.
   - **`predict`**, lengkap → emit `status` ("Menjalankan prediksi..."), insert `SensorRun`+`SensorReading` (reuse logic assignment-run dari `routes_sensor.py`), panggil `predict_failure()` lalu `_run_report_pipeline()` (fungsi yang sama dipakai `POST /sensor/readings`, dipanggil langsung sebagai fungsi Python — bukan HTTP self-call), dapat `ReportOut` → emit `prediction` (mapping dari `ReportOut.prediction`), emit `shap` (dari `ReportOut.shap`) kalau ada. **Kalau `prediction.label` True** (CRAG jalan di dalam `_run_report_pipeline()`), panggil `match_sop()` (lihat di bawah) dengan `ReportOut.root_cause_analysis.query` sebagai input teks, emit `sop` kalau ada match. **Kalau `prediction.label` False**, tidak ada event `sop` sama sekali (tidak ada masalah untuk diberi SOP). Terakhir emit `text` (dari `ReportOut.final_report`, diringkas untuk bubble chat kalau perlu).
   - **`latest_report`** → emit `status`, reuse logic query `GET /report/latest` untuk `machine_id`, kalau tidak ada laporan → emit `text` "Belum ada laporan untuk mesin ini." Kalau ada → mapping event sama seperti `predict` (termasuk aturan `sop` hanya kalau `label` True).
   - **`sop_lookup`** → emit `status`, query `GET /sops` (fetch-all), panggil `match_sop(sop_query, semua_sop)`, emit `sop` kalau ada match, emit `text` ringkasan singkat.
   - **`chitchat`** → `chat()` biasa (system prompt: asisten pemeliharaan prediktif CNC), emit `text` (di-chunk kata-per-kata).
4. **Persistensi** — satu mekanisme, dipakai di semua cabang: setelah semua event terkirim (termasuk cabang `needs_input`, yang teksnya sendiri jadi isi pesan), simpan SATU `ChatMessage` role=`assistant` berisi teks final gabungan (isi event `text`/`needs_input`), lalu tutup stream (frontend membaca sampai `reader.read()` selesai — tidak butuh event `[DONE]` khusus, lihat `backendStream()` di `route.ts`).

**`match_sop(query: str, sops: list[Sop]) -> Sop | None`** — helper bersama dipakai oleh cabang `predict`/`latest_report` (dengan `query` dari CRAG) maupun `sop_lookup` (dengan `query` dari `sop_query` user). Satu panggilan `chat_json()`: kirim `query` + daftar `{id, title, symptoms}` semua SOP, minta LLM balas `{"sop_id": "..." | null}` (null kalau tidak ada yang cukup relevan). Satu mekanisme pencocokan dipakai di semua tempat — bukan dua cara berbeda.

### Mapping `ReportOut` → event SSE

| `ReportOut` field | Event | Data |
|---|---|---|
| `prediction.label`, `.probability`, `.health_score` | `prediction` | `{label: bool, probability: float, healthScore: float, riskLevel: "rendah"\|"sedang"\|"tinggi"}` — `riskLevel` dihitung baru: `probability < 0.3` → rendah, `< 0.6` → sedang, else tinggi (threshold sederhana, didokumentasikan sebagai heuristik, bukan hasil tuning) |
| `shap.features` | `shap` | `{contributions: [{feature, value}]}` — mapping `feature_name`→`feature`, `shap_value`→`value` |
| Hasil `match_sop(root_cause_analysis.query, semua_sop)` — hanya kalau `prediction.label` True | `sop` | `{title, steps: [{id, text, priority, estimatedMinutes}]}` — kalau `match_sop` balas `None`, event ini di-skip (bukan dipaksa kosong) |
| `final_report` (markdown Bahasa Indonesia) | `text` | Teks lengkap, di-chunk untuk efek streaming |

### Skema request intent-classification (prompt `chat_json`)

Prompt system menjelaskan ke LLM: domain (predictive maintenance CNC Haas), 4 field sensor mentah yang valid (`air_temperature_k`, `process_temperature_k`, `rotational_speed_rpm`, `tool_wear_min`), daftar `machine_id`+nama mesin yang ada (di-query dulu dari `GET /machines` sebelum prompt disusun, supaya LLM bisa cocokkan nama mesin yang disebut user ke UUID asli) — bukan reasoning bebas, keluaran wajib JSON sesuai skema di atas (pakai `chat_json()` yang sudah mode JSON).

## Frontend

**`frontend/src/lib/types.ts`**:
- `PredictionResult`: hapus `failureType`/`failureTypeLabel` (taksonomi AI4I, tidak ada di backend), ganti jadi `{label: boolean, probability: number, healthScore: number, riskLevel: RiskLevel}`.
- `WomaiDataParts.downtime` tipe tetap ada (supaya `DowntimeEstimate` tidak perlu dihapus dari union — hanya tidak pernah dikirim backend), tidak ada perubahan struktural di sini.

**Komponen konsumsi `prediction`/`shap`/`sop` data-parts** (`frontend/src/components/chat/prediction-card.tsx` dan sejenisnya, kalau ada) — sesuaikan field yang dibaca sesuai `PredictionResult` baru. Field spesifik disesuaikan saat implementasi (baca file dulu, jangan asumsi struktur JSX).

**Tidak ada perubahan lain di frontend** — `route.ts` (proxy SSE) sudah benar dan tidak perlu diubah, mock fallback (`mockStream`) tetap ada sebagai graceful degradation kalau backend down (tidak dihapus).

## Testing & Verifikasi

- Backend: verifikasi statis (baca kode, cek `response_model`/SSE format) plus, kalau Docker+`.env` tersedia, `curl -N` ke `/chat` dengan `Accept: text/event-stream` untuk beberapa skenario: (a) pesan dengan semua field sensor lengkap + nama mesin valid → expect event `prediction`+`shap`+`text`; (b) pesan sensor tidak lengkap → expect `needs_input`; (c) "lihat laporan terakhir mesin X" → expect `prediction`+`text` dari data existing; (d) "bagaimana cara menangani overheat?" → expect `sop`; (e) "halo" → expect `text` saja (chitchat).
- Frontend: `bunx tsc --noEmit`, `bun run lint`, `bun run build`, `bun run test` — gate yang sama dipakai sub-project sebelumnya.
- Manual E2E (kalau environment memungkinkan): buka `/chat`, kirim pesan dengan deskripsi kondisi mesin, verifikasi respons datang dari backend asli (bukan mock — bisa dicek lewat `docker compose logs backend` menunjukkan request masuk).

## Di Luar Scope

- Halaman Knowledgebase (upload/list/hapus dokumen) — sub-project terpisah setelahnya.
- Halaman Dashboard/Report analitik terpisah (gauge, sparkline, tabel KNN mandiri) — dilarang rubrik AIC untuk penyisihan.
- Admin panel kelola user/role (`GET /users`, `PATCH /users/{id}/role`) — sesuai keputusan skip, dilarang rubrik AIC sebagai "sistem otentikasi kompleks".
- `GET /machines/{id}/status` — item kecil terpisah, bisa masuk task lain (tambah badge di halaman Mesin), tidak esensial untuk `/chat`.
- Native tool-calling Groq (`tools=`) dan streaming token asli — didefer, router intent + pseudo-streaming sudah cukup untuk MVP dan jauh lebih rendah risiko dalam waktu terbatas.
- Auto-tuning model, background job, atau pipeline logging otomatis — dilarang eksplisit oleh rubrik AIC untuk babak penyisihan.
