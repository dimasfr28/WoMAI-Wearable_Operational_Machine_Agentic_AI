# Spec Desain — Fondasi Frontend WO.M.AI di comfest-18 (Scaffold + Auth)

Tanggal: 2026-08-11
Status: disetujui untuk perencanaan implementasi

## Ringkasan

Sub-project pertama dari migrasi frontend `wo_m_ai` (Next.js 16, chat-first) ke repo `comfest-18` (saat ini React 18 + Vite, dashboard-first). Migrasi penuh dipecah jadi 4 sub-project independen karena mencakup subsistem yang beda-beda (auth, akses data, backend agent/chat, frontend UI); sub-project ini adalah fondasi yang jadi prasyarat 3 sub-project berikutnya.

**Scope sub-project ini**: ganti total `comfest-18/frontend/` (Vite+JSX) dengan hasil port `wo_m_ai/frontend/` (Next.js 16 App Router, TypeScript, Tailwind v4, shadcn/ui, Bun), lengkap dengan tampilan UI-nya (chat, mesin, SOP, riwayat — data masih dummy), tapi **auth-nya sungguhan**: login/register/logout terhubung ke backend JWT `comfest-18` yang sudah ada (`POST /auth/login`, `POST /auth/register`), bukan Supabase Auth milik `wo_m_ai` asli.

**Di luar scope** (dikerjakan di sub-project 2-4 terpisah): data mesin/SOP/riwayat sungguhan dari backend, endpoint `/chat` + model ML/SHAP asli, wiring UI chat ke backend baru, RBAC di UI, nasib halaman Dashboard/Knowledgebase/Report lama.

## Konteks: dua proyek yang dibandingkan

- `comfest-18` (repo ini): FastAPI + SQLAlchemy backend dengan model RandomForest asli, SHAP asli, Corrective RAG (ChromaDB + MinerU + Groq), JWT auth (python-jose), frontend React 18 + Vite SPA dashboard-first.
- `wo_m_ai` (`../wo_m_ai/`, sebelumnya bernama Predixia — direbrand di commit `a25641e`, remote GitHub `predixia-ai` → `wo-m-ai`): FastAPI + LangGraph deep-agent backend chat-first, prediksi ML **masih heuristik rule-based** (bukan model terlatih), explainability berupa lookup table statis (bukan SHAP sungguhan), SOP retrieval dari 5 dokumen hardcoded + RedisVL (bukan RAG dari PDF manual asli), auth Supabase, data access Drizzle ORM langsung ke Postgres dari frontend.

Kesimpulan yang mendasari keputusan migrasi: `wo_m_ai` punya orkestrasi agent/UX yang lebih matang, `comfest-18` punya model ML/SHAP/RAG yang benar-benar berfungsi. Sub-project 3 (di luar scope dokumen ini) akan menyambungkan pipeline agent `wo_m_ai` ke model asli `comfest-18`.

## Keputusan Utama

| Aspek | Keputusan |
|---|---|
| Frontend lama (Vite) | Dihapus total, diganti langsung (bukan berdampingan) |
| Package manager | Bun (ikut `wo_m_ai` asli, bukan npm) |
| Pola integrasi backend | BFF — semua panggilan ke `comfest-18` backend terjadi di server (Server Actions/Route Handlers), tidak ada fetch langsung dari browser |
| Auth | JWT `comfest-18` (`POST /auth/login`, `POST /auth/register`), bukan Supabase |
| Penyimpanan token | httpOnly cookie, di-set oleh Server Action setelah login sukses |
| Verifikasi token di middleware | Cek keberadaan cookie saja (tanpa verifikasi signature/expiry) — validasi sungguhan terjadi di backend saat Server Action lain memanggil REST API; 401 → hapus cookie + redirect `/login` |
| Halaman register | Disertakan (`/register`, panggil `POST /auth/register` — bootstrap, hanya jalan sekali saat tabel `users` kosong) |
| Isi halaman selain login (Chat/Mesin/SOP/Riwayat) | Tampilan `wo_m_ai` disalin apa adanya dengan data dummy in-memory (bukan placeholder kosong) |
| PWA (manifest, service worker, offline shell) | Ikut disalin apa adanya |
| Pendekatan porting kode | Copy total dari `wo_m_ai/frontend/` lalu langsung hapus/ganti bagian tak kompatibel (Drizzle, Supabase) di sub-project ini juga — tidak dibiarkan jadi kode mati |

## Arsitektur & Deployment

- Next.js 16 App Router jalan sebagai server sendiri (`next start` / standalone output untuk production) — **bukan** lagi static build di belakang Nginx seperti Vite app lama.
- `frontend/Dockerfile` diganti pola multi-stage `wo_m_ai` (stage `dev` hot-reload, stage `runner` production).
- Env var `BACKEND_URL` (mis. `http://backend:8000` di dalam Docker network internal, `http://localhost:8002` untuk dev lokal tanpa Docker) menggantikan seluruh env var Supabase (`NEXT_PUBLIC_SUPABASE_URL`, dst.) dan `VITE_API_BASE_URL` lama.
- `docker-compose.yml`: service `frontend` diperbarui — build arg `VITE_API_BASE_URL` diganti env `BACKEND_URL`; mapping port berubah dari `3000:80` (Nginx) jadi `3000:3000` (port default `next start`), host tetap `3000` jadi tidak ada perubahan yang terlihat user.
- Tidak perlu `JWT_SECRET` di frontend sama sekali (keputusan: middleware cuma cek keberadaan cookie).

## Perubahan File

**Dihapus dari `comfest-18/frontend/` (sisa Vite lama):**
`src/App.jsx`, `src/main.jsx`, `src/index.css`, `src/api/`, `src/components/MachineContext.jsx`, `src/pages/*.jsx`, `vite.config.js`, `index.html`, `nginx.conf`, `package-lock.json`, `Dockerfile` lama, `.dockerignore` lama.

**Disalin apa adanya dari `wo_m_ai/frontend/`:**
Seluruh `src/app/`, `src/components/` (termasuk `ui/`, `chat/`), `src/hooks/`, sebagian besar `src/lib/` (`format.ts`, `title.ts`, `risk.ts`, `types.ts`, `utils.ts`, `mock/`), `public/`, `src/app/manifest.ts`, `public/sw.js`, `ServiceWorkerRegister`, halaman `/offline`, konfigurasi (`tsconfig.json`, `postcss.config.mjs`, `eslint.config.mjs`, `components.json`, `next.config.ts`), `Dockerfile`, `.gitignore`, `.dockerignore`.

**Dihapus segera (tidak kompatibel dengan arsitektur `comfest-18`):**
`src/lib/db/`, `src/lib/supabase/`, `drizzle/`, `drizzle.config.ts`; dependency `drizzle-orm`, `drizzle-kit`, `@supabase/ssr`, `@supabase/supabase-js`, `postgres` di `package.json`.

**Ditulis ulang:**
- `src/middleware.ts` — logic Supabase diganti cek-cookie sederhana (lihat Alur Data).
- `src/app/actions/auth.ts` — diganti panggil `POST /auth/login` & `POST /auth/register` milik `comfest-18` + kelola cookie httpOnly. Ini satu-satunya Server Action yang benar-benar terhubung ke backend sungguhan di sub-project ini.
- `src/app/actions/machines.ts`, `sop.ts`, `sessions.ts` — isi query Drizzle diganti dummy array in-memory dengan bentuk/tipe data (TypeScript interface) yang sama persis dengan aslinya, supaya komponen UI dan hook (`use-machines.ts`, `use-sops.ts`, `use-sessions.ts`) tidak perlu diubah. Aksi CRUD (tambah/edit/hapus mesin, SOP) tetap bisa diklik tapi hanya mengubah state lokal (tidak persist) — ditandai toast singkat "Demo: perubahan belum tersimpan".
- `src/app/login/page.tsx` — UI dipakai ulang, submit diarahkan ke Server Action baru.
- `src/app/register/page.tsx` — halaman baru (tidak ada di `wo_m_ai`), form ke `POST /auth/register`.

**Tidak disentuh:**
`src/app/api/chat/route.ts` — logic fallback-ke-mock yang sudah ada otomatis terpakai apa adanya, karena `{BACKEND_URL}/chat` milik `comfest-18` belum ada (baru dibuat di sub-project 3), sehingga selalu jatuh ke `mockStream()`. Tidak ada perubahan kode diperlukan di file ini untuk sub-project ini.

## Alur Data

**Login:**
```
Browser → Server Action login(formData)
        → fetch POST {BACKEND_URL}/auth/login {username, password}
        → sukses: set httpOnly cookie "session" = access_token → redirect /chat
        → gagal (401): tampilkan "Username atau password salah" di form
        → network error: tampilkan "Server tidak terjangkau, coba lagi"
```

**Setiap load halaman terproteksi:**
```
middleware.ts → cookie "session" ada?
   tidak ada → redirect /login?next=<path asal>
   ada       → lanjut render halaman
```

**Register (bootstrap):**
```
Server Action register(formData) → POST /auth/register
   sukses → redirect /login dengan pesan "Akun dibuat, silakan login"
   403 (tabel users sudah terisi) → tampilkan "Registrasi publik ditutup, hubungi admin"
     (sesuai perilaku asli endpoint ini di backend comfest-18 — publik hanya
     dibuka sekali saat tabel users masih kosong, setelah itu lewat
     /auth/register/admin oleh admin)
```

**Token kadaluarsa di tengah sesi:** pola disiapkan sekarang di helper bersama (`lib/auth/session.ts`) walau baru relevan penuh mulai sub-project 2 — Server Action manapun yang menerima 401 dari backend → hapus cookie → redirect `/login?next=<path>`, supaya begitu login ulang user kembali ke halaman yang sama.

**Logout:** Server Action hapus cookie → redirect `/login`.

**Mesin/SOP/Riwayat/Chat:** murni jalur dummy/mock yang sudah ada di kode `wo_m_ai`, tidak ada penanganan error baru diperlukan untuk sub-project ini.

## Testing & Verifikasi

- Test Vitest yang sudah ada di `wo_m_ai` (`format.test.ts`, `title.test.ts`, `scenarios.test.ts`) ikut disalin, tetap jalan tanpa perubahan.
- Test baru: helper cookie (set/get/clear session) dan Server Action `login`/`register`/`logout` di `app/actions/auth.ts` — fetch ke backend di-mock, verifikasi cookie ter-set/terhapus dengan benar dan redirect/pesan error sesuai skenario.
- Quality gate: `bun run lint`, `bunx tsc --noEmit`, `bun run build`.
- Verifikasi manual end-to-end: login pakai user asli yang sudah ada di database `comfest-18` → masuk ke shell chat → buka Mesin/SOP/Riwayat (data dummy tampil) → logout → coba akses `/chat` langsung dalam kondisi logout → harus ke-redirect ke `/login`.

## Di Luar Scope (YAGNI untuk sub-project ini)

- Data mesin/SOP/riwayat sungguhan dari backend `comfest-18` (sub-project 2 — perlu endpoint CRUD SOP baru karena `comfest-18` saat ini berbasis PDF, bukan tabel SOP terstruktur).
- Endpoint `/chat` sungguhan + model ML/SHAP asli (sub-project 3 — port pipeline LangGraph `wo_m_ai` disambungkan ke `predictor.py`/`shap_tool.py` asli `comfest-18`).
- Wiring UI chat ke backend baru (sub-project 4).
- RBAC (viewer/engineer/admin) — role tersimpan di token tapi belum ditegakkan di UI manapun.
- Nasib halaman Dashboard/Knowledgebase/Report lama milik `comfest-18` — keputusan terpisah, tidak menghalangi sub-project ini.
