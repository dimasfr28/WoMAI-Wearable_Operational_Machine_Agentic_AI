# Spec Desain — Halaman Report (bukan Dashboard)

Tanggal: 2026-08-14
Status: disetujui untuk perencanaan implementasi

## Konteks

Frontend Next.js (branch `ariel`) tidak punya padanan untuk `DashboardPage.jsx`/`ReportPage.jsx` milik frontend Vite lama (`../comfest-18-1.0/frontend/src/pages/`) — endpoint `GET /report/latest` sama sekali belum dikonsumsi frontend manapun di `ariel`. Sudah dibahas dan disepakati bersama user: **Dashboard tidak dibangun ulang** (gauge, sparkline "Live Data", panel Status/AI Early Warning — persis "dashboard analitik tingkat lanjut" yang dilarang rubrik AIC penyisihan untuk `Kesiapan MVP` 15%). **Report dibangun**, karena isinya adalah output AI untuk satu query/prediksi (bukan monitoring berkelanjutan lintas waktu) — lebih dekat ke "menampilkan output dari AI" yang justru diwajibkan rubrik, bukan yang dilarang.

## Keputusan Utama

| Aspek | Keputusan |
|---|---|
| Halaman baru | `/report` — nama "Laporan" di UI (konsisten dengan "Mesin"/"SOP File"/"Riwayat" yang sudah ada di sidebar) |
| Backend | **Tidak ada logic baru** — murni reuse `GET /report/latest?machine_id=` yang sudah ada dan sudah bekerja, tidak disentuh sama sekali |
| Pemilihan mesin | Dropdown mesin di halaman (reuse `useMachines()`), plus opsional `?machine_id=` di URL untuk pre-select. Tanpa param, default ke mesin pertama dari `GET /machines` |
| Trigger | (1) Item sidebar baru "Laporan" (nav biasa, konsisten Mesin/SOP/Riwayat). (2) Link kontekstual di dekat pemilih mesin pada halaman chat (`MachinePicker`), aktif begitu ada mesin terpilih di chat, deep-link ke `/report?machine_id=<mesin terpilih>` — pakai state mesin yang SUDAH ada di client, **tanpa mengubah kontrak SSE `/chat` sama sekali** |
| Placeholder — belum ada request | Kalau halaman dibuka tanpa konteks permintaan baru (nav langsung/refresh), tetap panggil `GET /report/latest` untuk mesin yang aktif (bukan blank/error) — user melihat laporan **terakhir** yang pernah ada untuk mesin itu |
| Placeholder — benar-benar belum pernah ada | Kalau `GET /report/latest` 404 (belum pernah ada sensor reading/prediksi sama sekali untuk mesin itu), setiap kartu tampilkan **"N/A"**/"Belum ada laporan" — bukan halaman error, bukan kosong tanpa penjelasan |
| Di luar scope | Dashboard, sparkline historis, panel Status/AI Early Warning, auto-refresh/polling — semuanya TIDAK dibangun |

## Konten Halaman (reuse `ReportOut` apa adanya)

Mengikuti struktur `ReportPage.jsx` lama (`../comfest-18-1.0/frontend/src/pages/ReportPage.jsx`) sebagai referensi tata letak, di-porting ke shadcn/ui (bukan CSS custom lama), field dipetakan 1:1 dari `ReportOut` (`backend/app/schemas/report.py`, sudah final, tidak berubah):

1. **Health Score & Failure Risk** — dua kartu ringkas: `prediction.health_score` (/100), `prediction.failure_probability` (%) + label risiko + threshold.
2. **Sensor Terbaru** — tabel `sensor.{air_temperature_k, process_temperature_k, rotational_speed_rpm, tool_wear_min}` + badge FAILURE/NORMAL + `prediction.model_version`.
3. **SHAP — Fitur Paling Berpengaruh** — bar horizontal per `shap.features[]` (feature_name, shap_value, rank) + `shap.base_value`. Gaya visual boleh mirip `frontend/src/components/chat/shap-card.tsx` yang sudah ada (satu hasil, bukan tren — konsisten dengan alasan kenapa Report ini dianggap aman).
4. **Worst-Case Delta** — list `recommendations.worst_case_delta.suggested_adjustments` (map fitur→delta).
5. **Kasus Serupa (KNN)** — dua tabel kecil: `recommendations.nearest_failure`/`nearest_no_failure` (masing-masing beberapa baris {air_temperature_k, process_temperature_k, rotational_speed_rpm, tool_wear_min}). Ini tabel perbandingan multi-baris — TETAP dipertahankan sesuai keputusan user (bagian dari "output AI" untuk laporan ini, bukan monitoring terpisah), bukan dianggap melanggar karena terikat ke satu laporan, bukan tren historis mandiri.
6. **Root Cause Analysis** — `root_cause.query`/`.answer` (markdown) + badge sumber (`used_web_fallback` → "web (fallback)" vs "knowledgebase") + `retrieved_chunks[]` dalam `<details>` collapsible (opsional, boleh disederhanakan jadi jumlah chunk saja kalau `retrieved_chunks` kosong tapi `retrieved_chunk_ids` ada — cek behavior aktual saat implementasi). Kartu ini **tidak dirender** kalau `root_cause` null (prediksi tidak menunjukkan failure — konsisten dengan backend yang memang tidak menjalankan CRAG untuk kasus non-failure).
7. **Estimasi Harga Part** — tabel `part_prices[]` ({part_name, price_min, price_max, currency, source_url}), atau pesan "belum ada listing ditemukan" kalau array kosong.
8. **Laporan Akhir** — `final_report_text` (markdown) + `llm_model`.

Semua field di atas sudah dihitung backend sekali saat data sensor masuk (`_run_report_pipeline()`, tidak berubah oleh spec ini) — halaman ini murni tampilan, tidak trigger komputasi apa pun.

## Frontend

- **Type baru** `frontend/src/lib/types.ts`: `ReportData` — camelCase mapping dari `ReportOut` (semua field di atas).
- **Server Action baru** `frontend/src/app/actions/report.ts`: `getLatestReportAction(machineId: string): Promise<ReportData | null>` — pakai `backendFetch()` (pola sama seperti `machines.ts`/`sop.ts`), return `null` pada 404 (bukan throw) supaya halaman bisa render placeholder "N/A" dengan mulus.
- **Halaman baru** `frontend/src/app/(app)/report/page.tsx` — baca `?machine_id=` dari `useSearchParams`, dropdown pilih mesin (reuse `useMachines()`), panggil `getLatestReportAction`, render 8 kartu di atas atau placeholder N/A per kartu kalau `null`.
- **Sidebar** `frontend/src/components/app-sidebar.tsx` — tambah `SidebarMenuItem` "Laporan" (ikon lucide yang relevan, mis. `FileBarChart` atau serupa — pilih saat implementasi, cek ikon yang sudah dipakai supaya tidak duplikat), setelah item "Riwayat", mengikuti pola persis item lain di grup yang sama.
- **Link kontekstual dari chat**: di dekat `MachinePicker` (`frontend/src/components/chat/machine-picker.tsx` atau `chat-input.tsx`, cek lokasi tepat saat implementasi) — link/tombol kecil "Lihat laporan lengkap" yang aktif (enabled) begitu ada mesin terpilih, `href="/report?machine_id=<id>"`. Tidak butuh perubahan ke `route.ts` (proxy SSE) atau kontrak event backend sama sekali — murni pakai state mesin yang sudah ada di client.

## Testing & Verifikasi

- Frontend: `bunx tsc --noEmit`, `bun run lint`, `bun run build`, `bun run test` — gate yang sama dipakai sub-project sebelumnya.
- Backend: tidak ada perubahan, tidak perlu verifikasi ulang.
- Manual (kalau environment memungkinkan): buka `/report` tanpa param → default ke mesin pertama; pilih mesin yang punya laporan → semua 8 kartu terisi; pilih mesin yang belum pernah ada sensor reading → semua kartu placeholder "N/A"/"Belum ada laporan", bukan error; dari `/chat`, pilih mesin di `MachinePicker`, klik "Lihat laporan lengkap" → mendarat di `/report?machine_id=<mesin yang sama>`.

## Di Luar Scope

- Dashboard (gauge Health Score/Failure Risk/Prediction Stability, panel Sensor Monitoring "Live Data", Status card, AI Early Warning) — tidak dibangun, ini yang paling jelas melanggar batasan MVP rubrik AIC.
- Auto-refresh/polling — halaman ini tampilan statis per-kunjungan, ada tombol "Refresh" manual (reuse pola tombol refresh yang sudah ada di halaman lain seperti Mesin/SOP) tapi tidak ada interval otomatis.
- Endpoint `GET /report/history` — tidak dikonsumsi di spec ini (riwayat laporan lintas waktu = kembali ke wilayah "dashboard analitik"/"halaman riwayat penggunaan" yang dilarang rubrik).
- Perubahan apa pun ke backend, ke kontrak SSE `/chat`, atau ke `ReportOut`.
