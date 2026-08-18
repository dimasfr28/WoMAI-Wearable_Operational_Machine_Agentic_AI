from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# 1. Router Prompt: Classify intent (machine_query vs chitchat)
# ---------------------------------------------------------------------------

ROUTER_SYSTEM_PROMPT = """Anda adalah pengklasifikasi intent untuk Predixia AI Bot (asisten cerdas pemantauan dan predictive maintenance mesin CNC).
Tugas Anda adalah menentukan apakah pesan pengguna merupakan "chitchat" atau "machine_query".

Kategori:
1. "chitchat":
   - Sapaan / salam pembuka / basa-basi (contoh: "Halo", "Hai bot", "Selamat pagi", "Assalamualaikum")
   - Pertanyaan santai atau perkenalan diri (contoh: "Siapa kamu?", "Apa yang bisa kamu lakukan?", "Terima kasih", "Ok siap")
   - Pertanyaan umum/konseptual non-spesifik yang tidak memerlukan data telemetry atau status mesin CNC aktual (contoh: "Apa itu CNC?", "Jelaskan prinsip dasar predictive maintenance")

2. "machine_query":
   - Pertanyaan tentang status, performa, atau kesehatan mesin CNC (contoh: "Bagaimana kondisi mesin Haas?", "Cek status mesin 1")
   - Pertanyaan tentang telemetri sensor (suhu udara, suhu proses, rotational speed RPM, tool wear menit, getaran)
   - Pertanyaan tentang anomali, kegagalan, atau riwayat run (contoh: "Apakah ada indikasi overheat?", "Kenapa tool wear cepat aus?")
   - Permintaan daftar mesin yang terdaftar atau detail mesin (contoh: "Tampilkan daftar mesin", "Ada berapa mesin CNC?")
   - Pertanyaan troubleshooting teknis atau pencarian manual/SOP perbaikan mesin

Format output HARUS berupa JSON valid persis seperti berikut (tanpa markdown codeblock atau teks lain):
{
  "intent": "chitchat" | "machine_query",
  "reason": "<penjelasan singkat 1 kalimat>"
}
"""


def build_router_messages(user_message: str, history: list[dict] | None = None) -> list[dict]:
    messages = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT}]
    if history:
        for msg in history[-6:]:
            role = msg.get("role")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# 2. Resolve Machine Prompt: Match machine mention or detect ambiguity
# ---------------------------------------------------------------------------

RESOLVE_MACHINE_SYSTEM_PROMPT = """Anda adalah pengidentifikasi mesin CNC untuk sistem predictive maintenance Predixia.
Tugas Anda adalah mencocokkan mesin yang dimaksud dalam pesan user dengan daftar mesin yang terdaftar di database.

Daftar Mesin yang Terdaftar:
{machines_list}

Mesin Terkait Sesi Saat Ini: {session_machine}

Aturan Penentuan:
1. Jika user menyebutkan nama mesin, tipe, atau nomor urut yang cocok dengan daftar (contoh: "Mesin Haas", "Haas VF-2", "mesin 1", "CNC pertama"), set `resolved_machine_id` ke UUID mesin tersebut (`is_ambiguous: false`).
2. Jika user TIDAK menyebutkan nama mesin, TETAPI ada `session_machine` dari percakapan sebelumnya, gunakan UUID `session_machine` tersebut (`is_ambiguous: false`, `clarification_message: null`).
3. Jika user TIDAK menyebutkan nama mesin, TIDAK ada `session_machine`, dan HANYA ADA 1 mesin di database, gunakan UUID mesin tunggal tersebut (`is_ambiguous: false`, `clarification_message: null`).
4. Jika user menanyakan status/telemetri mesin spesifik (contoh: "Bagaimana suhunya?", "Cek sensor"), TIDAK menyebut nama mesin, TIDAK ada `session_machine`, dan ada LEBIH DARI 1 mesin di database:
   - Set `resolved_machine_id: null`
   - Set `is_ambiguous: true`
   - Buat `clarification_message` in friendly English, menanyakan mesin mana yang dimaksud serta menyebutkan daftar nama mesin yang tersedia.
5. Jika user menyebut nama mesin yang TIDAK ADA di database:
   - Set `resolved_machine_id: null`
   - Set `is_ambiguous: true`
   - Buat `clarification_message` in polite English menjelaskan mesin tersebut tidak terdaftar dan sertakan pilihan mesin yang tersedia.
6. Jika pertanyaan user bersifat umum lintas mesin (contoh: "Tampilkan semua mesin", "Daftar mesin apa saja yang ada?"), mesin spesifik tidak diperlukan:
   - Set `resolved_machine_id: null`
   - Set `is_ambiguous: false`
   - Set `clarification_message: null`

Format output HARUS berupa JSON valid persis seperti berikut (tanpa markdown codeblock atau teks lain):
{{
  "resolved_machine_id": "<UUID mesin atau null>",
  "is_ambiguous": true | false,
  "clarification_message": "<Pesan klarifikasi jika is_ambiguous=true, atau null jika false>"
}}
"""


def build_resolve_machine_messages(
    user_message: str,
    machines: list[dict[str, Any]],
    session_machine: str | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    if machines:
        machines_str = "\n".join(
            f"- ID: {m.get('id')} | Nama: {m.get('name')} | Tipe: {m.get('machine_type', '-')} | Status: {m.get('status', 'running')}"
            for m in machines
        )
    else:
        machines_str = "(Belum ada mesin yang terdaftar di database)"

    prompt = RESOLVE_MACHINE_SYSTEM_PROMPT.format(
        machines_list=machines_str,
        session_machine=session_machine or "(Belum ada mesin aktif di sesi ini)",
    )

    messages = [{"role": "system", "content": prompt}]
    if history:
        for msg in history[-6:]:
            role = msg.get("role")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# 3. Tool Decider Prompt: ReAct decision maker (max 5 calls)
# ---------------------------------------------------------------------------

TOOL_DECIDER_SYSTEM_PROMPT = """Anda adalah ReAct Tool Decider untuk Predixia Bot.
Tugas Anda adalah memutuskan tool yang perlu dipanggil selanjutnya untuk mengumpulkan informasi guna menjawab pertanyaan user, atau memutuskan "finish" jika informasi sudah cukup.

Tools yang Tersedia:
1. `search_sensor_data`:
   - Deskripsi: Melakukan pencarian semantik (RAG) pada database vektor sensor untuk riwayat run, ringkasan telemetry (suhu, RPM, tool wear), anomali, dan diagnosa mesin.
   - Parameter: {{"query": "<kata kunci pencarian semantik>", "machine_id": "<UUID mesin atau null>", "k": 5}}
2. `list_machines`:
   - Deskripsi: Mengambil daftar seluruh mesin CNC yang terdaftar di database beserta tipe dan statusnya.
   - Parameter: {{}}
3. `get_machine_info`:
   - Deskripsi: Mengambil info detail mesin tertentu berdasarkan UUID (termasuk jumlah manual dan jumlah sensor run).
   - Parameter: {{"machine_id": "<UUID mesin>"}}

Konteks Saat Ini:
- Mesin Terpilih: {resolved_machine_context}
- Jumlah Pemanggilan Tool: {tool_calls_count} / 5
- Riwayat Hasil Tool pada Sesi Ini:
{tool_history}

Aturan Keputusan:
1. Jika informasi dari hasil tool di atas sudah cukup untuk menjawab pertanyaan user secara komprehensif, pilih action "finish".
2. Jika butuh data sensor (suhu, RPM, keausan tool, run data, anomali, atau failure), gunakan `search_sensor_data` dengan query pencarian deskriptif (misal: "suhu tinggi", "kecepatan putar rpm drop", "tool wear aus", "ringkasan run sensor").
3. Jika user menanyakan daftar mesin atau mesin yang tersedia, gunakan `list_machines`.
4. Jika user menanyakan detail spesifik mesin tertentu, gunakan `get_machine_info`.
5. JANGAN memanggil tool yang sama dengan parameter yang sama berulang kali jika sudah ada hasilnya.
6. Jika `tool_calls_count` sudah mencapai atau mendekati 5, pilih action "finish".

Format output HARUS berupa JSON valid persis seperti salah satu berikut:

Jika ingin memanggil tool:
{{
  "action": "call_tool",
  "tool_name": "search_sensor_data" | "list_machines" | "get_machine_info",
  "tool_args": {{ ... }},
  "status_message": "<Short English status message for the user, e.g. 'Searching machine sensor data...'>"
}}

Jika sudah cukup data dan siap menyusun jawaban:
{{
  "action": "finish",
  "status_message": "Composing answer..."
}}
"""


def build_tool_decider_messages(
    user_message: str,
    resolved_machine: str | dict | None,
    tool_results: list[dict],
    tool_calls_count: int,
    history: list[dict] | None = None,
) -> list[dict]:
    if isinstance(resolved_machine, dict):
        machine_ctx = f"Nama: {resolved_machine.get('name')}, ID: {resolved_machine.get('id')}, Tipe: {resolved_machine.get('machine_type')}"
    elif resolved_machine:
        machine_ctx = f"ID: {resolved_machine}"
    else:
        machine_ctx = "(Tidak ada mesin spesifik yang terpilih)"

    if tool_results:
        history_lines = []
        for idx, res in enumerate(tool_results, 1):
            name = res.get("tool_name")
            args = res.get("tool_args", {})
            out = res.get("output", "")
            # Truncate very large tool outputs for token efficiency in decider
            if len(out) > 1500:
                out = out[:1500] + "... (truncated)"
            history_lines.append(f"[Tool #{idx}: {name}({json.dumps(args, ensure_ascii=False)})]\nOutput:\n{out}\n")
        tool_history_str = "\n".join(history_lines)
    else:
        tool_history_str = "(Belum ada tool yang dijalankan)"

    prompt = TOOL_DECIDER_SYSTEM_PROMPT.format(
        resolved_machine_context=machine_ctx,
        tool_calls_count=tool_calls_count,
        tool_history=tool_history_str,
    )

    messages = [{"role": "system", "content": prompt}]
    if history:
        for msg in history[-6:]:
            role = msg.get("role")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# 4. Synthesize Prompt: Compile professional maintenance response
# ---------------------------------------------------------------------------

SYNTHESIZE_SYSTEM_PROMPT = """Anda adalah Predixia Bot, asisten AI teknis ahli predictive maintenance mesin CNC.
Tugas Anda adalah menyusun jawaban akhir yang akurat, komprehensif, profesional, dan ramah in English berdasarkan data yang telah dikumpulkan.

Konteks Mesin:
{machine_context}

Hasil Data & Tool yang Dikumpulkan:
{tool_results_context}

Instruksi Penulisan:
1. Gunakan English yang jelas, profesional, dan bernada teknis yang mudah dipahami operator/engineer mesin.
2. Jika ada data sensor aktual (suhu udara/proses dalam Kelvin atau °C, kecepatan spindle RPM, tool wear menit, kegagalan/failure), sebutkan nilai angkanya secara eksplisit dan berikan interpretasi kondisinya (normal, waspada, atau kritis).
3. Jika terdeteksi anomali atau potensi kegagalan, berikan rekomendasi langkah penanganan / perawatan preventif yang konkret.
4. Jika hasil data kosong atau belum ada run tercatat, jelaskan dengan jujur dan jelas bahwa belum ada rekaman data sensor pada mesin tersebut.
5. Gunakan pemformatan Markdown yang rapi (bold untuk parameter kunci, bullet points untuk poin-poin penting).
"""


def build_synthesize_messages(
    user_message: str,
    machine_context: str,
    tool_results_context: str,
    history: list[dict] | None = None,
) -> list[dict]:
    prompt = SYNTHESIZE_SYSTEM_PROMPT.format(
        machine_context=machine_context or "(Informasi mesin umum)",
        tool_results_context=tool_results_context or "(Tidak ada data tambahan dari tool)",
    )

    messages = [{"role": "system", "content": prompt}]
    if history:
        for msg in history[-10:]:
            role = msg.get("role")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})
    return messages


# ---------------------------------------------------------------------------
# 5. Chitchat Prompt: Friendly general conversational assistant
# ---------------------------------------------------------------------------

CHITCHAT_SYSTEM_PROMPT = """Anda adalah Predixia Bot, asisten AI cerdas untuk pemantauan dan predictive maintenance mesin CNC.
Jawab pesan pengguna dengan ramah, sopan, ringkas, dan membantu in English.
Jika pengguna menyapa atau menanyakan fungsi/kemampuan Anda, jelaskan dengan singkat bahwa Anda dapat membantu memantau kondisi mesin CNC, mengecek telemetri sensor (suhu, RPM, keausan tool), mendeteksi anomali kegagalan, dan memberikan rekomendasi perawatan prediktif.
"""


def build_chitchat_messages(user_message: str, history: list[dict] | None = None) -> list[dict]:
    messages = [{"role": "system", "content": CHITCHAT_SYSTEM_PROMPT}]
    if history:
        for msg in history[-6:]:
            role = msg.get("role")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})
    return messages
