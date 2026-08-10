"""PDF document chunking — ported VERBATIM from /home/dimas/comfest/code/knowledgebase.ipynb
(cells 6, 7, 8). Do not "improve" the algorithm here; any behavior change must
also change the reference notebook and chunks.json, which this module must stay
byte-for-byte compatible with.

Source cells:
  - cell 6: _parse_table_grid, LIGATURE_WORD_MAP, fix_ligatures, clean_html
  - cell 7: Heading dataclass, HEADING_RE, STEP_HEADING_RE, parse_headings, normalize_headings
  - cell 8: _step_number, find_step_runs, build_chunks
"""
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# cell 6 — table grid parsing, ligature fix, HTML -> plain text
# ---------------------------------------------------------------------------


def _parse_table_grid(table_tag):
    """Ubah <table> jadi grid 2D string, menangani rowspan/colspan (sel yang di-span
    diduplikasi ke sel-sel yang tercakup supaya tiap baris output tetap punya nilai lengkap).
    Mengembalikan (grid, span_marker) — span_marker[r][c] True kalau sel itu hasil duplikasi
    dari rowspan/colspan (bukan sel asli), supaya tidak dihitung dobel saat build pairs."""
    rows_raw = table_tag.find_all("tr")
    if not rows_raw:
        return [], []
    grid, span_marker = [], []
    pending = {}  # col_idx -> (sisa_rowspan, text)

    for row in rows_raw:
        cells = row.find_all(["td", "th"])
        grid_row, span_row = [], []
        col_idx = 0

        def next_free_col(c):
            while c in pending and pending[c][0] > 0:
                grid_row.append(pending[c][1])
                span_row.append(True)
                if pending[c][0] - 1 <= 0:
                    del pending[c]
                else:
                    pending[c] = (pending[c][0] - 1, pending[c][1])
                c += 1
            return c

        col_idx = next_free_col(col_idx)
        for cell in cells:
            col_idx = next_free_col(col_idx)
            text = cell.get_text(strip=True)
            colspan = int(cell.get("colspan", 1) or 1)
            rowspan = int(cell.get("rowspan", 1) or 1)
            for k in range(colspan):
                grid_row.append(text)
                span_row.append(k > 0)  # kolom ke-2+ dari colspan = duplikat, jangan didobel di output
                if rowspan > 1:
                    pending[col_idx + k] = (rowspan - 1, text)
            col_idx += colspan
            col_idx = next_free_col(col_idx)
        col_idx = next_free_col(col_idx)
        grid.append(grid_row)
        span_marker.append(span_row)

    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    span_marker = [r + [False] * (width - len(r)) for r in span_marker]
    return grid, span_marker


# Bug OCR MinerU: ligature Unicode "fi/fl/ff" kadang gagal ter-decode dan jadi null byte
# (mis. "o\x00ngers" -> "fingers", "shut o\x00" -> "shut off"). Mapping whole-word ini
# diverifikasi manual dari kata-kata yang ditemukan di dokumen manual Haas; fallback "fi"
# dipakai untuk kata yang tidak dikenal (kasus paling umum untuk ligature ini).
LIGATURE_WORD_MAP = {
    "\x00ag": "flag",
    "\x00ange": "flange",
    "\x00at": "flat",
    "\x00eld-replaceable": "field-replaceable",
    "\x00le": "file",
    "\x00llout": "fillout",
    "\x00nd": "find",
    "\x00nger,": "finger,",
    "\x00ngers": "fingers",
    "\x00ngers,": "fingers,",
    "\x00ow": "flow",
    "\x00ow,": "flow,",
    "\x00ow.": "flow.",
    "\x00rst": "first",
    "\x00tting": "fitting",
    "\x00ush": "flush",
    "\x00xture": "fixture",
    "V-\x00ange": "V-flange",
    "con\x00rms": "confirms",
    "di\x00erent": "different",
    "di\x00erentiate": "differentiate",
    "e\x00ort": "effort",
    "mu\x00er": "muffler",
    "o\x00": "off",
    "o\x00set": "offset",
    "o\x00set,": "offset,",
    "ori\x00ce": "orifice",
    "recon\x00gure": "reconfigure",
    "speci\x00cations:": "specifications:",
    "su\x00cient": "sufficient",
    "veri\x00cation": "verification",
}


def fix_ligatures(text: str) -> str:
    if "\x00" not in text:
        return text
    return re.sub(
        r"\S*\x00\S*",
        lambda m: LIGATURE_WORD_MAP.get(m.group(), m.group().replace("\x00", "fi")),
        text,
    )


def clean_html(text: str) -> str:
    """Konversi HTML sisa hasil ekstraksi PDF (table, br, sub, strong, dll) menjadi plain text.

    Tabel: baris pertama selalu dipakai sebagai nama kolom (banyak tabel hasil OCR PDF tidak
    memakai <th>, header-nya berupa <td> biasa di baris pertama). rowspan/colspan ditangani
    supaya baris yang sel-nya "digabung" tetap mengacu ke nama kolom yang benar, bukan
    "Column 1/2/3" generik.
    """
    text = fix_ligatures(text)

    if "<" not in text:
        return text

    soup = BeautifulSoup(text, "html.parser")

    for table in soup.find_all("table"):
        grid, span_marker = _parse_table_grid(table)
        lines = []
        if grid:
            header = grid[0]
            for row, spans in zip(grid[1:], span_marker[1:]):
                if all(not c.strip() for c in row):
                    continue
                pairs = [f"{h}: {v}" for h, v, is_span in zip(header, row, spans) if not is_span and h.strip()]
                lines.append(", ".join(pairs))
        table.replace_with("\n".join(lines))

    for tag in soup.find_all(["br"]):
        tag.replace_with("\n")
    for tag in soup.find_all(["p", "div"]):
        tag.append("\n")

    plain = soup.get_text()
    plain = re.sub(r"[ \t]+\n", "\n", plain)
    plain = re.sub(r"\n{3,}", "\n\n", plain)
    return plain.strip()


# Alias — nama yang dipakai di RANCANGAN_SISTEM.md Section 6.2 untuk fungsi yang
# sama persis dengan clean_html() di notebook (nama asli dipertahankan di atas).
clean_html_fragment = clean_html


# ---------------------------------------------------------------------------
# cell 7 — Heading parsing & normalization
# ---------------------------------------------------------------------------


@dataclass
class Heading:
    level: int          # 1 atau 2
    text: str
    position: int        # posisi karakter di dokumen (awal baris heading)
    content: str = ""     # isi di antara heading ini dan heading berikutnya


HEADING_RE = re.compile(r"^(#{1,2})[ \t]+(.*?)[ \t]*$", re.MULTILINE)


def parse_headings(md_text: str) -> list[Heading]:
    """1. Parsing Heading — ambil semua heading level 1-2 beserta level, text, posisi."""
    matches = list(HEADING_RE.finditer(md_text))
    headings = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        text = m.group(2).strip()
        start_content = m.end()
        end_content = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        content = md_text[start_content:end_content].strip()
        headings.append(Heading(level=level, text=text, position=m.start(), content=content))
    return headings


# Heading level-2 yang mengandung "[" atau "{" bukan heading sungguhan — itu
# instruksi tombol/kode (mis. "Push [ZERO RETURN].", "Push [DIAGNOSTIC].",
# "Press {F1}") yang salah ter-OCR MinerU jadi heading terpisah.
FALSE_HEADING_CHARS_RE = re.compile(r"[\[\{]")


def _is_false_heading(h: Heading) -> bool:
    return h.level == 2 and FALSE_HEADING_CHARS_RE.search(h.text) is not None


def strip_false_headings(headings: list[Heading]) -> list[Heading]:
    """Rule 0 (paling awal, sebelum normalisasi/klasifikasi lain): heading
    level-2 yang mengandung "[" atau "{" di-downgrade jadi teks biasa —
    digabung sebagai TAMBAHAN content ke heading sebelumnya, bukan diproses
    sebagai SECTION_TITLE/STEP_NUMBER/STEP_SUBTITLE. Ini menghindari section
    palsu seperti "## Push [ZERO RETURN]." memutus rangkaian step atau
    membuat chunk sendiri yang tidak seharusnya ada.

    Kalau heading palsu ini muncul sebagai heading PERTAMA (tidak ada heading
    sebelumnya untuk digabung), dia tetap dipertahankan apa adanya — kasus ini
    sangat jarang dan lebih aman daripada membuang informasi.
    """
    result: list[Heading] = []
    for h in headings:
        if _is_false_heading(h) and result:
            prev = result[-1]
            extra = h.text if not h.content else f"{h.text}\n\n{h.content}"
            prev.content = f"{prev.content}\n\n{extra}".strip() if prev.content else extra
            continue
        result.append(h)
    return result


def normalize_headings(headings: list[Heading]) -> list[Heading]:
    """2. Normalisasi Heading — Rule A saja: gabungkan heading level-1 berurutan
    tanpa isi di antaranya (mis. OCR memecah judul BAB jadi 2 baris `#` terpisah).

    Rule-Based Hierarchy Reconstruction (lihat build_chunks/find_step_runs)
    menggantikan Rule B/C lama sepenuhnya — heading level-2 tidak lagi
    dinormalisasi/digabung sebelum klasifikasi STEP_NUMBER vs SECTION_TITLE.
    """
    result: list[Heading] = []
    i = 0
    n = len(headings)
    while i < n:
        h = headings[i]
        if h.level == 1 and not h.content and i + 1 < n and headings[i + 1].level == 1:
            merged_text = h.text
            j = i
            while j + 1 < n and headings[j].level == 1 and not headings[j].content and headings[j + 1].level == 1:
                merged_text += "\n" + headings[j + 1].text
                j += 1
            result.append(Heading(level=1, text=merged_text, position=h.position, content=headings[j].content))
            i = j + 1
            continue
        result.append(h)
        i += 1
    return result


# ---------------------------------------------------------------------------
# cell 8 — Rule-Based Hierarchy Reconstruction: STEP_NUMBER vs SECTION_TITLE
# ---------------------------------------------------------------------------

# Rule 2: heading level-2 dianggap STEP_NUMBER HANYA kalau isinya angka bulat
# murni (mis. "1", "2", "10") -- TIDAK ADA teks lain. Heading angka yang diikuti
# teks (mis. "1.", "1) ", "Step 3") TIDAK dianggap STEP_NUMBER, melainkan
# SECTION_TITLE (Rule 3/4).
PURE_STEP_NUMBER_RE = re.compile(r"^\d{1,2}$")

# Rule 5: toleransi gap antar nomor STEP_NUMBER berurutan dalam satu rangkaian
# prosedur (mis. 1, 3, 4 tetap 1 rangkaian meski nomor "2" hilang akibat OCR;
# 1, 7, 8 dianggap rangkaian baru karena lompatannya terlalu jauh).
MAX_STEP_GAP = 2


def _is_step_number(h: Heading) -> bool:
    """Rule 2 & 3: True hanya untuk heading level-2 berupa angka bulat MURNI."""
    return h.level == 2 and PURE_STEP_NUMBER_RE.match(h.text.strip()) is not None


def _step_value(h: Heading) -> int | None:
    return int(h.text.strip()) if _is_step_number(h) else None


def find_step_runs(section_headings: list[Heading], max_gap: int = MAX_STEP_GAP) -> list[list[int]]:
    """Rule 5: analisis urutan STEP_NUMBER dalam satu section_group. Sebuah
    rangkaian (run) berlanjut selama nomor STEP_NUMBER berikutnya:
      - MASIH NAIK dibanding nomor sebelumnya (next > current), DAN
      - selisihnya <= max_gap (mis. 1,3,4 -> gap 1->3 = 2, masih toleransi
        untuk nomor yang hilang akibat kesalahan ekstraksi OCR).

    Run baru dimulai kalau salah satu kondisi berikut terjadi:
      1. next <= current -- nomor turun atau mengulang (mis. "2" lalu "1",
         atau "3" lalu "3") -- ini hampir pasti restart numbering, awal
         prosedur baru yang heading pemisahnya hilang akibat OCR (skenario
         nyata: "...Set Grid Offset" step "2" lalu langsung "1" -> "2" -> ...
         "6" milik prosedur "Set Tool Change Offset" yang berbeda).
      2. next - current > max_gap -- lompatan nomor terlalu jauh (mis. 1,7,8).

    Kembalikan list of run; tiap run = list index (relatif ke section_headings)
    heading STEP_NUMBER yang tergabung jadi satu rangkaian prosedur. Run dengan
    hanya 1 anggota TETAP dikembalikan (satu step berdiri sendiri masih dianggap
    bagian dari section induknya, lihat build_chunks) — pemfilteran run
    "signifikan" (>=2) adalah keputusan build_chunks, bukan fungsi ini.
    """
    numbers = [_step_value(h) for h in section_headings]
    numeric_idx = [i for i, v in enumerate(numbers) if v is not None]
    if not numeric_idx:
        return []

    runs: list[list[int]] = [[numeric_idx[0]]]
    for prev_i, cur_i in zip(numeric_idx, numeric_idx[1:]):
        current, nxt = numbers[prev_i], numbers[cur_i]
        starts_new_run = nxt <= current or (nxt - current) > max_gap
        if starts_new_run:
            runs.append([cur_i])
        else:
            runs[-1].append(cur_i)
    return runs


def _classify_section_group(section_group: list[Heading]) -> tuple[list[str], dict[int, int]]:
    """Klasifikasi tiap heading dalam satu section_group jadi salah satu:
      - "step": STEP_NUMBER (angka murni, Rule 2).
      - "subtitle": SECTION_TITLE yang berada DI ANTARA dua STEP_NUMBER dari
        RANGKAIAN find_step_runs YANG SAMA (Rule 5: gap <= MAX_STEP_GAP) —
        artinya rangkaian step itu BELUM selesai (masih ada STEP_NUMBER lain
        menyusul dalam rangkaian yang sama). Heading ini bagian dari step yang
        sedang aktif, BUKAN pembuka chunk baru.
      - "title": SECTION_TITLE asli — SEBELUM STEP_NUMBER pertama, SETELAH
        STEP_NUMBER TERAKHIR dari rangkaiannya (tidak ada step lagi menyusul
        DALAM RANGKAIAN YANG SAMA), atau berada di antara dua rangkaian
        find_step_runs YANG BERBEDA (lompatan nomor terlalu jauh, Rule 5).
        Selalu membuka chunk baru.

    Rule tambahan (di luar Rule 1-6 dasar): sebuah rangkaian STEP dianggap
    masih aktif HANYA selama masih ada STEP_NUMBER berikutnya DALAM RANGKAIAN
    YANG SAMA (find_step_runs). Begitu STEP_NUMBER terakhir dari rangkaian itu
    selesai, SECTION_TITLE berikutnya SELALU dianggap section baru — walau
    posisinya "menempel" tepat setelah step terakhir (mis. "Push
    [DIAGNOSTIC]." setelah "## 3" dianggap title baru, bukan bagian Step 3,
    karena tidak ada step lain sesudahnya). Ini trade-off yang disengaja demi
    predictability: tanpa penanda struktural tambahan, heading yang menempel
    ke step terakhir tidak bisa dibedakan secara aman dari section informatif
    baru (mis. "Verification").

    Mengembalikan (categories, run_id_of) — run_id_of dipakai build_chunks
    untuk mendeteksi pergantian rangkaian STEP_NUMBER (mis. "2,3" lalu "1,2,3"
    setelah step MENURUN/restart, Rule 5 tambahan) supaya rangkaian yang
    menurun tidak salah tertampung ke chunk step run SEBELUMNYA.
    """
    n = len(section_group)
    runs = find_step_runs(section_group)
    run_id_of: dict[int, int] = {}
    for run_id, run in enumerate(runs):
        for idx in run:
            run_id_of[idx] = run_id

    categories = [""] * n
    for idx, h2 in enumerate(section_group):
        if _is_step_number(h2):
            categories[idx] = "step"
            continue
        prev_step_idx = max((p for p in run_id_of if p < idx), default=None)
        next_step_idx = min((p for p in run_id_of if p > idx), default=None)
        same_run = (
            prev_step_idx is not None
            and next_step_idx is not None
            and run_id_of[prev_step_idx] == run_id_of[next_step_idx]
        )
        categories[idx] = "subtitle" if same_run else "title"
    return categories, run_id_of


def eliminate_empty_headings(section_group: list[Heading]) -> list[Heading]:
    """Rule 6 — Empty Heading Elimination: sebuah heading level-2 adalah
    PARENT heading (bukan chunk sendiri) apabila content-nya KOSONG dan
    langsung diikuti heading level-2 lain. Parent digabung jadi PATH JALUR
    (breadcrumb, dipisah " > ") ke LEAF heading berikutnya dalam rangkaian
    itu — leaf ditentukan murni struktural: heading yang TIDAK langsung
    diikuti heading lain sebelum konten apa pun muncul (teks, gambar, tabel —
    heading yang isinya cuma gambar markdown tetap leaf, karena "kosong" di
    sini berarti content.strip() == "", bukan soal jenis kontennya).

    Mengembalikan list Heading baru (bisa lebih pendek dari input) — parent
    heading yang tereliminasi TIDAK punya entri sendiri lagi, teksnya sudah
    melebur ke heading_2 leaf berikutnya.
    """
    result: list[Heading] = []
    i = 0
    n = len(section_group)
    while i < n:
        h = section_group[i]
        path_parts: list[str] = []
        j = i
        while not h.content.strip() and j + 1 < n:
            path_parts.append(h.text)
            j += 1
            h = section_group[j]
        if path_parts:
            merged_text = " > ".join(path_parts + [h.text])
            result.append(Heading(level=h.level, text=merged_text, position=h.position, content=h.content))
        else:
            result.append(h)
        i = j + 1
    return result


def build_chunks(headings: list[Heading], doc_name: str, machine_type: str = "Haas") -> list[dict]:
    """4. Rule-Based Hierarchy Reconstruction:

    - Heading level-1 -> selalu Top-Level Section (current_h1), tidak pernah
      membuat chunk sendiri.
    - Dalam satu section_group: parent heading kosong dieliminasi lebih dulu
      (Rule 6, lihat eliminate_empty_headings), lalu setiap heading yang
      tersisa diklasifikasi "step", "subtitle", atau "title" (lihat
      _classify_section_group). Heading "title" membuka chunk baru; heading
      "step" dan "subtitle" tergabung sebagai isi chunk yang sedang aktif
      (step jadi "Step N", subtitle jadi teks sub-judul biasa di content).
    - Tanpa STEP_NUMBER sama sekali dalam section_group -> semua heading
      berkategori "title", perilaku jadi sama seperti section biasa.
    """
    chunks = []
    i = 0
    n = len(headings)
    current_h1 = ""

    while i < n:
        h = headings[i]
        if h.level == 1:
            current_h1 = clean_html(h.text)
            i += 1
            continue

        # Kumpulkan seluruh heading level-2 berurutan (sampai next level-1) sebagai satu section group.
        j = i
        while j < n and headings[j].level == 2:
            j += 1
        section_group = eliminate_empty_headings(headings[i:j])
        categories, run_id_of = _classify_section_group(section_group)

        pending_title_idx: int | None = None
        pending_parts: list[str] = []
        pending_run_id: int | None = None  # run_id STEP_NUMBER yang sedang tertampung

        def flush() -> None:
            nonlocal pending_title_idx, pending_parts, pending_run_id
            if pending_title_idx is None:
                return
            title_heading = section_group[pending_title_idx]
            # clean_html (bukan cuma fix_ligatures): heading text sendiri kadang
            # mengandung tag HTML mentah (mis. "<sub>Important:</sub> ...")
            # hasil OCR MinerU, sama seperti content.
            heading_2_text = clean_html(title_heading.text)
            full_content = clean_html("\n\n".join(p for p in pending_parts if p))
            chunks.append({
                "doc": doc_name,
                "machine_type": machine_type,
                "heading_1": current_h1,
                "heading_2": heading_2_text,
                "content": f"{current_h1}\n\n{heading_2_text}\n\n{full_content}".strip(),
            })
            pending_title_idx = None
            pending_parts = []
            pending_run_id = None

        for idx, h2 in enumerate(section_group):
            cat = categories[idx]
            if cat == "title":
                flush()
                pending_title_idx = idx
                pending_parts = [h2.content] if h2.content.strip() else []
                continue

            # "step" atau "subtitle": tergabung ke chunk yang sedang aktif —
            # KECUALI ini step yang run_id-nya beda dari run yang sedang
            # tertampung (mis. rangkaian "2,3" lalu step MENURUN/restart ke
            # "1,2,3", find_step_runs sudah memisahkannya jadi run berbeda):
            # itu harus memicu chunk baru, bukan tertimpa ke chunk lama, sebab
            # tidak ada "title" baru yang muncul di antara dua step yatim ini
            # untuk memicu flush secara alami.
            this_run_id = run_id_of.get(idx)
            if cat == "step" and pending_run_id is not None and this_run_id != pending_run_id:
                flush()

            # STEP_NUMBER yatim (section_group dimulai dengan step tanpa
            # SECTION_TITLE di depannya) -- pakai step itu sendiri sebagai
            # pembuka chunk (jarang terjadi; dokumen normal selalu punya
            # judul sebelum step pertama).
            if pending_title_idx is None:
                pending_title_idx = idx
                pending_parts = []
            body = h2.content.strip()
            if cat == "step":
                pending_run_id = this_run_id
                label = f"Step {_step_value(h2)}"
                pending_parts.append(f"{label}\n\n{body}" if body else label)
            else:  # subtitle
                pending_parts.append(f"{h2.text.strip()}\n\n{body}" if body else h2.text.strip())

        flush()
        i = j

    return chunks


def build_document_chunks(md_text: str, doc_name: str, machine_type: str = "Haas") -> list[dict]:
    """Entry point pipeline penuh: parse -> strip false headings -> normalize -> build chunks.
    Output schema identik chunks.json: {"doc", "machine_type", "heading_1", "heading_2", "content"}.
    """
    headings = normalize_headings(strip_false_headings(parse_headings(md_text)))
    return build_chunks(headings, doc_name=doc_name, machine_type=machine_type)
