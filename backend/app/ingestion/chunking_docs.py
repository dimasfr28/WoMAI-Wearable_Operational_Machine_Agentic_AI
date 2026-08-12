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
# cell 8 (revisi): 1 chunk per heading_1 — semua heading level-2 (dan
# kontennya) di bawah satu heading level-1 digabung jadi satu chunk besar,
# alih-alih dipecah lagi per heading_2/step seperti versi Rule-Based Hierarchy
# Reconstruction sebelumnya. Chunk jadi lebih sedikit dan lebih panjang/utuh
# konteksnya per section, dengan trade-off presisi semantic search yang lebih
# rendah dibanding chunk granular — perubahan ini disengaja (permintaan user).
# ---------------------------------------------------------------------------

# Markdown image syntax hasil OCR MinerU (mis. "![](images/8f8e27a6...jpg)")
# — dibuang dari isi chunk karena base64/path gambar tidak berguna untuk
# embedding/semantic search dan cuma menambah noise pada teks.
IMAGE_MARKDOWN_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def strip_images(text: str) -> str:
    text = IMAGE_MARKDOWN_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_chunks(headings: list[Heading], doc_name: str, machine_type: str = "Haas") -> list[dict]:
    """Group heading level-2 (title/subtitle/step, semuanya tanpa dibedakan
    lagi) di bawah satu heading level-1 jadi SATU chunk. Heading level-1 tanpa
    heading level-2 sama sekali (section langsung berisi teks, jarang tapi
    mungkin) tetap menghasilkan satu chunk dengan heading_2 kosong.
    """
    chunks: list[dict] = []
    i = 0
    n = len(headings)
    current_h1 = ""
    pending_parts: list[str] = []

    def flush() -> None:
        nonlocal pending_parts
        if not current_h1 and not pending_parts:
            return
        full_content = strip_images(clean_html("\n\n".join(p for p in pending_parts if p.strip())))
        chunks.append({
            "doc": doc_name,
            "machine_type": machine_type,
            "heading_1": current_h1,
            "heading_2": "",
            "content": strip_images(f"{current_h1}\n\n{full_content}".strip()),
        })
        pending_parts = []

    while i < n:
        h = headings[i]
        if h.level == 1:
            flush()
            current_h1 = clean_html(h.text)
            i += 1
            continue

        # clean_html: heading_2 text sendiri kadang mengandung tag HTML mentah
        # (mis. "<sub>Important:</sub> ...") hasil OCR MinerU, sama seperti content.
        heading_2_text = clean_html(h.text)
        body = h.content.strip()
        pending_parts.append(f"{heading_2_text}\n\n{body}" if body else heading_2_text)
        i += 1

    flush()
    return chunks


def build_document_chunks(md_text: str, doc_name: str, machine_type: str = "Haas") -> list[dict]:
    """Entry point pipeline penuh: parse -> strip false headings -> normalize -> build chunks.
    Output schema identik chunks.json: {"doc", "machine_type", "heading_1", "heading_2", "content"}.
    """
    headings = normalize_headings(strip_false_headings(parse_headings(md_text)))
    return build_chunks(headings, doc_name=doc_name, machine_type=machine_type)
