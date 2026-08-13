# Spec Desain — Wiring Mesin & SOP ke Backend Sungguhan

Tanggal: 2026-08-13
Status: disetujui untuk perencanaan implementasi

## Ringkasan

Sub-project kedua dari migrasi frontend WO.M.AI ke `comfest-18` (sub-project pertama: `docs/superpowers/specs/2026-08-11-womai-frontend-foundation-design.md`). Sub-project 1 hanya menyambungkan auth ke backend sungguhan — halaman `/mesin` dan `/sop` masih pakai in-memory dummy store, tidak pernah memanggil backend REST API sama sekali. Sub-project ini menyambungkan keduanya ke data sungguhan.

Ditemukan dua kesenjangan nyata antara desain dummy frontend (diwarisi dari `wo_m_ai`, berbasis dataset AI4I 2020) dan domain `comfest-18` yang sebenarnya:

1. **Machine**: field dummy `type: "L"|"M"|"H"` / `line` / `notes` tidak berkorespondensi dengan apa pun di skema backend (`name`, `machine_type` teks bebas default `"Haas"`, `status`, `document_count`, `run_count`). Backend juga cuma punya `GET`/`POST /machines` — tidak ada edit/delete.
2. **SOP**: backend `comfest-18` tidak punya konsep SOP terstruktur sama sekali — prediksi ML-nya biner (`predicted_label: bool`, dijelaskan SHAP per-fitur sensor), bukan taksonomi failure-mode TWF/HDF/PWF/OSF/RNF ala AI4I yang dipakai dummy data. Root-cause analysis yang sudah ada (`app/rag/`, CRAG) berbasis PDF knowledgebase + LLM, konsepnya beda dari "library SOP yang di-manage manual."

## Keputusan Utama

| Aspek | Keputusan |
|---|---|
| Scope | Machines + SOP dikerjakan sekaligus dalam satu sub-project |
| Skema Machine | FE disesuaikan ke skema backend asli (`name` + `machine_type` teks bebas) — bukan sebaliknya. Tampilkan `status`/`document_count`/`run_count` (data nyata, belum pernah ditampilkan FE manapun) |
| Edit/Delete Machine | Tambah `PATCH`/`DELETE /machines/{id}` di backend (role `engineer`+), supaya FE tidak kehilangan fungsi dibanding versi dummy |
| Delete Machine + data terkait | `409 Conflict` kalau mesin masih punya dokumen/sensor run — bukan cascade delete diam-diam |
| Konsep SOP | Library SOP mandiri, TANPA field `mode`/failure-taxonomy — murni prosedur yang di-manage manual, terpisah dari sistem CRAG/knowledgebase PDF yang sudah ada |
| Scope SOP | Global lintas semua mesin (bukan per-`machine_id`) — sama seperti desain asli `wo_m_ai` |
| Steps SOP | Disimpan sebagai JSONB (konsisten dengan pola `Recommendation.payload` yang sudah ada), bukan tabel anak terpisah |
| RBAC mutasi SOP | `require_role("engineer")` untuk create/update/delete, `GET` publik — konsisten dengan pola `POST /machines`/upload knowledgebase yang sudah ada |
| Pola integrasi FE | Server Actions (`actions/machines.ts`, `actions/sop.ts`) diganti dari in-memory store ke `fetch()` + `Authorization: Bearer` pakai `requireSession()` — pola sama persis dengan `actions/auth.ts` di sub-project 1. Nama/signature fungsi tidak berubah, jadi `lib/machines.ts`/`lib/sops.ts` dan semua hook/halaman yang memanggilnya tidak perlu diubah |

## Backend: Machines

**Endpoint baru** di `routes_machine.py`:
- `PATCH /machines/{id}` — `require_role("engineer")`, body `MachineUpdateIn { name?: str, machine_type?: str }` (partial update)
- `DELETE /machines/{id}` — `require_role("engineer")`. Cek dulu: kalau mesin masih punya `documents` atau `sensor_runs`, balas `409 Conflict` dengan pesan jelas alih-alih cascade delete diam-diam.

**Schema baru** di `schemas/machine.py`: `MachineUpdateIn`.

Tidak ada migrasi DB baru untuk Machine — tabel `machines` sudah lengkap (`name`, `machine_type`, `status`, `created_at`).

## Backend: SOP (fitur baru)

**Migrasi baru** `0010_sop_library.py`, tabel `sops`:
```python
sa.Column("id", UUID, primary_key=True, default=gen_uuid)
sa.Column("title", sa.String(255), nullable=False)
sa.Column("symptoms", sa.Text, nullable=False, server_default="")
sa.Column("body", sa.Text, nullable=False, server_default="")
sa.Column("steps", JSONB, nullable=False, server_default="[]")
sa.Column("reference", sa.Text, nullable=False, server_default="")
sa.Column("created_by", UUID, sa.ForeignKey("users.id"), nullable=True)
sa.Column("created_at", DateTime(timezone=True), server_default=func.now())
sa.Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```
`steps` berisi array `{id, text, priority, estimated_minutes}` — bentuk sama persis dengan yang sudah dipakai FE dummy, cuma sekarang persisten di Postgres.

**Schema baru** `schemas/sop.py`: `SopStepIn`/`SopStepOut { id, text, priority: Literal["segera","terjadwal"], estimated_minutes: int }`, `SopOut`, `SopCreateIn`, `SopUpdateIn` (semua field opsional untuk partial update).

**Route baru** `routes_sop.py`:
- `GET /sops` — publik (tanpa auth), konsisten dengan pola GET read-only lain di codebase ini
- `POST /sops` — `require_role("engineer")`
- `PATCH /sops/{id}` — `require_role("engineer")`
- `DELETE /sops/{id}` — `require_role("engineer")`

## Frontend

**`lib/types.ts`**:
- `Machine`: hapus `type`/`line`/`notes`; tambah `machineType?: string`, `status: string`, `documentCount: number`, `runCount: number`.
- `Sop`: hapus `mode`, `SopMode`, `SOP_MODE_LABEL`; field lain (`title`, `symptoms`, `body`, `steps`, `reference`, `createdAt`, `updatedAt`) tidak berubah.

**`actions/machines.ts`, `actions/sop.ts`**: isi diganti dari array in-memory ke `fetch()` sungguhan ke `{BACKEND_URL}/machines` dan `{BACKEND_URL}/sops`, pakai `requireSession()` untuk token dan header `Authorization: Bearer <token>` — pola identik `actions/auth.ts`. Nama/signature fungsi ekspor (`loadMachinesAction`, `saveMachineAction`, dst.) **tidak berubah**, jadi `lib/machines.ts`/`lib/sops.ts` dan seluruh hook/halaman pemanggil tidak perlu disentuh.

**Komponen UI**:
- `machine-form-dialog.tsx`: hapus Select Tipe (L/M/H), field Line, field Catatan → satu input teks `machine_type` (placeholder "Haas").
- `mesin/page.tsx`: list menampilkan badge status + jumlah dokumen/run (data nyata). Hapus catatan "Mode demo: perubahan belum tersimpan" (sudah tidak berlaku).
- `sop-form-dialog.tsx`: hapus Select mode. Field lain tidak berubah.
- `sop/page.tsx`: hapus catatan "Mode demo: perubahan belum tersimpan".

**Error handling**: ikuti pola `auth.ts` — 401 dari backend (token invalid/expired) → hapus cookie sesi, redirect ke `/login`; 403 (role kurang) → toast jelas "butuh role engineer" alih-alih pesan generik.

## Testing & Verifikasi

- Migrasi `0010_sop_library.py` dijalankan (`alembic upgrade head`) dan diverifikasi via `docker compose exec backend alembic upgrade head` (kalau environment memungkinkan) — atau divalidasi secara statis (review SQL yang di-generate) kalau tidak ada Docker/`.env` sungguhan tersedia.
- Endpoint backend baru diverifikasi via `curl`/Swagger (`/docs`) kalau backend bisa dijalankan; kalau tidak, verifikasi statis (baca kode, cek response_model, cek RBAC decorator) seperti pola yang sudah dipakai di sub-project sebelumnya untuk kondisi serupa.
- FE: `bunx tsc --noEmit`, `bun run lint`, `bun run build`, `bun run test` — sama seperti gate sub-project 1.
- Manual E2E (kalau ada `.env` sungguhan): login → buka `/mesin` → tambah/edit/hapus mesin sungguhan → buka `/sop` → tambah/edit/hapus SOP sungguhan → refresh halaman, konfirmasi data bertahan (bukti persistensi, beda dari sub-project 1 yang dummy).

## Di Luar Scope

- Halaman `/chat` dan endpoint `/chat` backend (agent pipeline) — sub-project terpisah.
- RBAC enforcement di level UI (menyembunyikan tombol untuk role rendah) — backend sudah menegakkan lewat `require_role`, tapi FE belum menyesuaikan tampilan berdasar role user saat ini.
- Migrasi data SOP dari sumber lain (tidak ada data SOP existing untuk di-migrasi — tabel baru dimulai kosong).
- Mengubah sistem knowledgebase PDF/CRAG yang sudah ada — SOP baru ini berdiri sendiri, tidak berinteraksi dengannya.
