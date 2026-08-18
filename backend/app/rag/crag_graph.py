"""RAG — Arsitektur CRAG dengan LangGraph — Section 6.9.

Dipanggil langsung (sinkron) oleh routes_report.py (Section 6.11) hanya ketika
predicted_label = True. BUKAN tool agent chatbot (chatbot belum dibangun fase
ini) — signature-nya tetap tool-ready untuk dipakai ulang nanti.
"""
from __future__ import annotations

import logging
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, END

from app.llm.gemini_client import chat, chat_json
from app.ml.outlier import RunIqrBounds, is_value_outlier
from app.rag.grader import grade_documents
from app.rag.part_price_search import searxng_search
from app.rag.retriever import RetrievedDocument, retrieve_documents

logger = logging.getLogger(__name__)


class CRAGState(TypedDict):
    query: str
    search_queries: list[str]
    machine_id: str | None
    documents: list[RetrievedDocument]
    grade: Literal["relevant", "irrelevant"]
    used_web_fallback: bool
    answer: str
    part_name: str | None
    part_names: list[str]


RAG_ANSWER_PROMPT = """You are a technical predictive maintenance assistant for CNC machines.
Using ONLY the sources below (service manuals / troubleshooting guides / historical sensor run
data), answer the query in English with EXACTLY three sections, each as its own heading:

## What Is the Problem
A direct, concise diagnosis: state which condition or failure the evidence indicates, based on
the sources and sensor data.

## Handling Procedure
Concrete, actionable steps the technician must follow to resolve this, based on the procedures
in the sources.

## Affected Part / Component
The SPECIFIC part or component that must be inspected or replaced — name a concrete technical
component that can be looked up on a marketplace (e.g. "spindle bearing", "ballscrew", "coolant
pump", "servo motor axis Z", "toolholder"), NOT a generic term like "Tool" or "Gearbox" alone.
Include the exact part number/code if the sources mention one.

CITATION RULE (mandatory): every claim you draw from a source MUST be followed by a citation
naming that source, in parentheses, using the source's exact name WITHOUT any file extension —
e.g. "(Haas Service Manual - VF_VM Spindle)", not "(Haas Service Manual - VF_VM Spindle.pdf)".
Use only the source names listed under "Sources" below — do not invent or guess a source name.
If a claim is not backed by any source, state it as your own technical inference and do not
attach a citation to it.

DIRECTNESS RULE (mandatory): write direct, definitive statements grounded in the evidence
provided. Do not hedge with vague filler words such as "maybe", "perhaps", "possibly", "it
seems", or "it might be" — if the evidence supports a conclusion, state it plainly; if it only
supports a partial conclusion, state precisely what the evidence does and does not show, rather
than softening the whole sentence with an ambiguous qualifier.

Query: {query}

Sources:
{context}

At the end of your answer, add a separate line in exactly this format, listing every distinct
part/component/consumable your "Handling Procedure" says must be REPLACED or ACTIVELY SERVICED
(e.g. replaced, swapped, refilled, re-greased) to fix the problem — always include the part named
in "Affected Part / Component" first. Do NOT include a part only mentioned in passing as something
to inspect/check/verify without being replaced or serviced, and do NOT use a bare generic word
like "filter" or "kit" alone — each entry must be a specific, marketplace-searchable product name
(include the machine/brand context, e.g. "Haas ballscrew" not "screw"; "CNC spindle grease" not
"grease"). Separate multiple items with commas, most important first:
PART_NAMES: <part 1>, <part 2>, ... <or "unknown" if none>
"""


def retrieve(state: CRAGState) -> CRAGState:
    """Multi-query retrieval: generate_search_queries() menghasilkan beberapa
    query (cause/troubleshooting/component/maintenance, lihat RAG_QUERY_PROMPT)
    — retrieve_documents() dipanggil SEKALI PER QUERY (bukan sekali untuk satu
    query gabungan) supaya tiap kategori kebutuhan informasi dapat porsi
    pencarian semantiknya sendiri, lalu semua hasil digabung & dedupe by
    chroma_id. k diperkecil per query (3, bukan 5) supaya total chunk yang
    masuk ke grading/prompt tidak meledak seiring bertambahnya jumlah query."""
    queries = state.get("search_queries") or [state["query"]]
    machine_id = state.get("machine_id")

    seen_ids: set[str] = set()
    merged: list[RetrievedDocument] = []
    for q in queries:
        for doc in retrieve_documents(q, k=3, machine_id=machine_id):
            chroma_id = doc.metadata.get("chroma_id")
            if chroma_id and chroma_id in seen_ids:
                continue
            if chroma_id:
                seen_ids.add(chroma_id)
            merged.append(doc)

    return {**state, "documents": merged}


def grade_documents_node(state: CRAGState) -> CRAGState:
    """LLM (Groq) menilai relevansi tiap dokumen terhadap query (yes/no),
    ambil rasio relevan; kalau < 50% dokumen relevan -> grade='irrelevant'."""
    grade, _verdicts = grade_documents(state["query"], state["documents"])
    return {**state, "grade": grade}


def web_search_searxng(state: CRAGState) -> CRAGState:
    results = searxng_search(state["query"], num_results=5)
    extra_docs = [
        RetrievedDocument(page_content=r["content"], metadata={"url": r["url"], "title": r.get("title", "")})
        for r in results
        if r.get("content")
    ]
    return {**state, "documents": state["documents"] + extra_docs, "used_web_fallback": True}


def extract_part_names(answer_text: str) -> list[str]:
    """Public (no leading underscore) — also used by routes_report.py's
    get_latest_report to re-derive the part list from a persisted rag_answer
    (RootCauseAnalysis doesn't store part_names as its own column). Parses the
    "PART_NAMES: <a>, <b>, ..." line RAG_ANSWER_PROMPT is instructed to emit —
    every part/consumable the Handling Procedure says needs replacing or
    servicing, used to build the Machine Report's multi-part cost table
    (rancangan.txt "Machine Report REVISI" point 6)."""
    for line in answer_text.splitlines():
        if line.strip().upper().startswith("PART_NAMES:"):
            value = line.split(":", 1)[1].strip()
            if not value or value.lower() == "unknown":
                return []
            return [p.strip() for p in value.split(",") if p.strip() and p.strip().lower() != "unknown"]
    return []


def extract_part_name(answer_text: str) -> str | None:
    """Primary part/component name (first entry of extract_part_names) —
    used for the single "Affected Part / Component" / Machine Parts Checking
    title, distinct from the full multi-part list used for pricing."""
    names = extract_part_names(answer_text)
    return names[0] if names else None


MAX_CHUNK_CHARS_IN_PROMPT = 800


def _source_name(metadata: dict) -> str:
    """Citation label for one retrieved chunk — extension-free document name
    for knowledge-base chunks (metadata["doc"] is already stored without a
    file extension, see routes_knowledgebase.py's doc_name), or the page
    title/domain for web-fallback results (no "doc" key)."""
    doc = metadata.get("doc")
    if doc:
        return doc
    title = metadata.get("title")
    if title:
        return title
    url = metadata.get("url")
    if url:
        return url
    return "unknown source"


def generate_answer(state: CRAGState) -> CRAGState:
    # Bug ditemukan lewat testing nyata: tanpa batas ini, 8 chunk (5 dari
    # knowledgebase_docs + 3 dari knowledgebase_sensor_runs) bisa total >30K
    # karakter (~9K+ token) — melebihi TPM 12000/menit Groq free tier begitu
    # ditambah prompt instruksi + jawaban, request ditolak 413 dan seluruh
    # analisis root cause jatuh ke fallback. grade_documents (grader.py) sudah
    # membatasi ke 800 char/dok untuk alasan yang sama; disamakan di sini.
    #
    # Each source is labeled with its citation name (Source: <name>) directly
    # above its content, so the LLM can cite it exactly rather than guessing
    # or inventing a document name.
    context = (
        "\n\n".join(
            f"Source: {_source_name(d.metadata)}\n{d.page_content[:MAX_CHUNK_CHARS_IN_PROMPT]}"
            for d in state["documents"]
        )
        or "(no sources found)"
    )
    prompt = RAG_ANSWER_PROMPT.format(query=state["query"], context=context)
    try:
        answer = chat([{"role": "user", "content": prompt}])
    except Exception:
        logger.exception("generate_answer: Groq call failed")
        answer = (
            "Automatic root-cause analysis is unavailable right now (LLM service unreachable). "
            "Please check the relevant service manual manually.\n"
            "PART_NAMES: unknown"
        )
    part_names = extract_part_names(answer)
    part_name = part_names[0] if part_names else None
    return {**state, "answer": answer, "part_name": part_name, "part_names": part_names}


def _build_graph():
    graph = StateGraph(CRAGState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade_documents", grade_documents_node)
    graph.add_node("web_search_searxng", web_search_searxng)
    graph.add_node("generate_answer", generate_answer)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "grade_documents")
    graph.add_conditional_edges(
        "grade_documents",
        lambda s: s["grade"],
        {"relevant": "generate_answer", "irrelevant": "web_search_searxng"},
    )
    graph.add_edge("web_search_searxng", "generate_answer")
    graph.add_edge("generate_answer", END)
    return graph.compile()


crag_app = _build_graph()


CAUSE_ANALYSIS_SHORT_PROMPT = """Summarize the root-cause analysis below into EXACTLY ONE
sentence in English, MAXIMUM 40 words. Name ONLY ONE part/component (the most relevant one) —
if the analysis below names more than one part, pick only the most relevant. Preserve any
citation from the analysis that supports the part you keep, in the same "(Source Name)" format
(no file extension) — drop citations tied to parts you are not keeping. Do not use
headings/markdown, do not include a "PART_NAMES:" line, reply with ONLY the one-sentence summary.

Write a direct, definitive statement. Do not hedge with vague filler words such as "maybe",
"perhaps", "possibly", "it seems", or "it might be" — state the conclusion the analysis supports
plainly.

Root-cause analysis:
{root_cause_answer}
"""


def summarize_cause_analysis(root_cause_answer: str) -> str:
    """"Cause Analysis LLM" ringkas untuk Machine Diagnosis "AI Explanation"
    panel (rancangan.txt Section 5) — meringkas jawaban CRAG penuh
    (RAG_ANSWER_PROMPT, 3 section) jadi maks 1 kalimat/40 kata, 1 part saja.
    Meringkas jawaban yang SUDAH ADA (bukan retrieval ulang) — lebih murah dan
    konsisten dengan analisis penuh yang sudah ditampilkan di root_cause.answer,
    tidak berisiko menyebut part berbeda dari root cause utama."""
    prompt = CAUSE_ANALYSIS_SHORT_PROMPT.format(root_cause_answer=root_cause_answer)
    try:
        summary = chat([{"role": "user", "content": prompt}], temperature=0.2)
        return summary.strip()
    except Exception:
        logger.exception("summarize_cause_analysis: Groq call failed")
        return "Automatic cause summary is unavailable right now — see the full analysis below."


def run_crag(query_text: str, machine_id: str | None = None, search_queries: list[str] | None = None) -> CRAGState:
    """Entry point used by routes_report.py. `query_text` is the single-string
    representation stored as RootCauseAnalysis.rag_query and used for grading/
    web-fallback; `search_queries` (from generate_search_queries) drives the
    actual multi-query retrieve() step — falls back to [query_text] if not
    provided (keeps this callable standalone, e.g. from a future chatbot)."""
    initial_state: CRAGState = {
        "query": query_text,
        "search_queries": search_queries or [query_text],
        "machine_id": machine_id,
        "documents": [],
        "grade": "irrelevant",
        "used_web_fallback": False,
        "answer": "",
        "part_name": None,
        "part_names": [],
    }
    return crag_app.invoke(initial_state)


# Mapping mentah -> istilah umum, dipakai untuk mengisi [TOP SHAP] di
# RAG_QUERY_PROMPT — persis daftar "VARIABLE NORMALIZATION" di rancangan.txt.
# LLM sendiri juga diinstruksikan melakukan normalisasi yang sama, tapi
# mengisi placeholder dengan istilah yang SUDAH dinormalisasi di sini membuat
# perilakunya tidak bergantung penuh pada LLM mematuhi instruksi normalisasi
# — kalau LLM lupa/salah, [TOP SHAP] yang disubstitusi tetap benar.
# Kunci: nama kolom model klasifikasi baru (lihat predictor_clasification.py's
# RAW_TO_MODEL_COL) — "air_temp_K" dst, bukan "Air temperature K".
_SHAP_FEATURE_TO_GENERAL_TERM = {
    "air_temp_K": "heat / temperature",
    "proc_temp_K": "heat / temperature",
    "rpm": "speed",
    "tool_wear_min": "machine operating time",
}


def _is_feature_anomalous(feature_name: str, value: float, run_bounds: RunIqrBounds | None) -> bool:
    """True kalau nilai fitur ini di luar IQR bounds RUN INI (rancangan.txt —
    IQR per RUN ID, menggantikan bound statis global training yang tidak ada
    lagi sejak model lama dihapus) — dipakai untuk MEMILIH top-SHAP mana yang
    genuinely anomali (bukan cuma "paling berkontribusi" tapi nilainya masih
    dalam rentang wajar; SHAP value bisa nonzero murni dari interaksi feature
    engineering)."""
    if run_bounds is None:
        return False
    if feature_name == "tool_wear_min":
        return is_value_outlier(value, run_bounds.tool_wear_min)
    if feature_name == "rpm":
        return is_value_outlier(value, run_bounds.rotational_speed_rpm)
    if feature_name == "air_temp_K":
        return is_value_outlier(value, run_bounds.air_temperature_k)
    if feature_name == "proc_temp_K":
        return is_value_outlier(value, run_bounds.process_temperature_k)
    return False


RAG_QUERY_PROMPT = """
You are a Query Rewriter for a predictive maintenance system.

Your task is to transform a machine failure root-cause analysis
into GENERAL and TECHNICAL English search queries for a RAG
knowledge base.

The retrieved knowledge may come from:

- machine service manuals
- machine troubleshooting manuals
- maintenance manuals
- operating manuals
- technical documentation
- repair guides
- maintenance procedures

The machine type is represented by:
{name_machine}

The variable with the strongest influence on the predicted failure
is represented by:
{top_shap}

==================================================
VARIABLE NORMALIZATION
==================================================

Convert machine-learning feature names into more general technical
terms that are likely to be understood and used in machine manuals.

Use the following mappings:

- "Air Temperature K" → "heat / temperature"
- "Process Temperature K" → "heat / temperature"
- "Rotational Speed rpm" → "speed"
- "Tool Wear min" → "machine operating time"

IMPORTANT:

The original feature names are machine-learning dataset features.
Do NOT use the raw feature names in the generated RAG queries.

For example:

"Air Temperature K"
→ "heat / temperature"

"Process Temperature K"
→ "heat / temperature"

"Rotational Speed rpm"
→ "speed"

"Tool Wear min"
→ "machine operating time"


==================================================
QUERY GENERATION RULES
==================================================

1. ALL GENERATED SEARCH QUERIES MUST BE IN ENGLISH.

2. DO NOT include specific numerical sensor values.

Examples:

"400 minutes"
→ "prolonged machine operating time"

"12.3 K"
→ "abnormal heat / temperature"

"1520 rpm"
→ "abnormal speed"

3. DO NOT include dataset-specific thresholds.

Example:

"machine operating time exceeded 192 minutes"
→ "prolonged machine operating time"

4. Do not include exact SHAP values in the query.

Use {top_shap} as the concept representing the variable
with the strongest influence on machine failure.

5. Do not use overly specific terminology that is only meaningful
to the dataset.

Use terminology that is likely to appear in real machine manuals,
service documentation, troubleshooting guides, and maintenance
procedures.

6. The machine name must be represented using:

{name_machine}

Do not hard-code a specific machine type such as CNC, Haas,
lathe, milling machine, or any other machine type.

7. Generate queries that cover DIFFERENT information needs.

The generated queries MUST cover:

A. FAILURE CAUSE / WHY

Query should investigate why {top_shap} can contribute to,
cause, or indicate machine failure.

Example:

"{name_machine} why abnormal heat or temperature can cause machine failure"

B. FAILURE HANDLING / TROUBLESHOOTING

Query should investigate how to diagnose, troubleshoot,
and handle machine failure associated with {top_shap}.

Example:

"{name_machine} troubleshooting machine failure caused by abnormal heat"

C. COMPONENT / PART

Query should investigate which components or parts may be affected
by or associated with the failure condition related to {top_shap}.

Example:

"{name_machine} components affected by overheating"

D. MAINTENANCE / REPAIR

Query should investigate maintenance, inspection, repair,
or corrective procedures related to {top_shap}.

Example:

"{name_machine} maintenance procedure for abnormal temperature"

8. If multiple abnormal conditions exist, generate additional
queries for each important condition.

9. Do NOT invent a specific component or part in the query unless
the root-cause evidence supports that component.

For example, do NOT automatically assume:

- spindle bearing
- servo motor
- coolant pump
- gearbox
- bearing

unless there is supporting evidence.

Instead, use a general query such as:

"{name_machine} components related to overheating"

10. The purpose of retrieval is to FIND evidence from the knowledge
base, not to make the final diagnosis.

Therefore, queries should be broad enough to achieve high recall
while remaining technically relevant.

11. Prefer combinations of:

- machine type
- normalized condition
- failure
- troubleshooting
- maintenance
- component
- cause

12. Avoid queries that contain only the variable name.

Bad:

"machine operating time"

Better:

"{name_machine} prolonged machine operating time failure troubleshooting"

13. Do not phrase queries with hedging or ambiguous qualifiers (e.g. "maybe",
"possibly", "might"). Queries are search strings, not claims, so state the
condition directly (e.g. "prolonged machine operating time", not "possibly
prolonged machine operating time").


==================================================
ROOT CAUSE INPUT
==================================================

Root Cause:
{root_cause}


==================================================
OUTPUT
==================================================

Return ONLY valid JSON using exactly this structure:

{{
  "normalized_conditions": [
    "...",
    "..."
  ],
  "search_queries": [
    "...",
    "...",
    "...",
    "..."
  ],
  "technical_keywords": [
    "...",
    "...",
    "..."
  ]
}}

The "normalized_conditions" field must contain the generalized
technical interpretation of the abnormal variables.

The "search_queries" field must contain multiple English queries
covering:

1. Why {top_shap} contributes to failure
2. How to troubleshoot or handle the failure
3. Which components or parts may be involved
4. Maintenance, inspection, or repair procedures

The "technical_keywords" field must contain generalized technical
terms useful for semantic retrieval.

Do not include numerical values, dataset thresholds,
SHAP values, or raw machine-learning feature names in the
search queries.
"""


def generate_search_queries(
    shap_result: dict,
    machine_name: str = "CNC machine",
    feature_row: dict | None = None,
    run_bounds: RunIqrBounds | None = None,
) -> tuple[str, list[str]]:
    """Query generation via LLM (rancangan.txt's RAG_QUERY_PROMPT) — mengganti
    build_root_cause_query()/_interpret_shap_feature() rule-based sebelumnya.
    Query sekarang ADAPTIF: LLM men-generate beberapa query bahasa Inggris
    (cause/troubleshooting/component/maintenance) dari deskripsi root-cause,
    bukan template kalimat hardcode per nama fitur.

    Root-cause description yang dikirim ke LLM tetap dibangun dari IQR bounds
    per RUN ID (_is_feature_anomalous, lihat app/ml/outlier.py) — bukan LLM
    yang menilai "apakah nilainya tinggi", supaya klaim anomali tetap berbasis
    statistik, bukan tebakan LLM. LLM hanya bertugas mengubah gejala itu jadi
    query pencarian yang adaptif dan general (tidak hardcode nama part/istilah
    dataset). `feature_row` parameter dipertahankan untuk kompatibilitas
    signature, tidak lagi dipakai langsung di sini (temp_diff dulu dihitung
    dari situ; sekarang bound per-fitur sudah cukup dari run_bounds).

    Returns (top_shap_term, search_queries) — top_shap_term dipakai sebagai
    representasi ringkas untuk RootCauseAnalysis.rag_query (kolom tunggal di
    DB), search_queries dipakai retrieve() untuk multi-query retrieval.
    """
    features = sorted(shap_result.get("features", []), key=lambda f: f["shap_value"], reverse=True)
    anomalous = [f for f in features if f["shap_value"] > 0 and _is_feature_anomalous(f["feature_name"], f["value"], run_bounds)]

    top_features = anomalous or [f for f in features if f["shap_value"] > 0] or features[:1]
    top_feature = top_features[0] if top_features else None
    top_shap_term = _SHAP_FEATURE_TO_GENERAL_TERM.get(
        top_feature["feature_name"], top_feature["feature_name"]
    ) if top_feature else "abnormal sensor reading"

    root_cause_lines = []
    for f in top_features[:3]:
        term = _SHAP_FEATURE_TO_GENERAL_TERM.get(f["feature_name"], f["feature_name"])
        root_cause_lines.append(f"- {f['feature_name']} (normalized: {term}), value={f['value']}")
    root_cause_text = "\n".join(root_cause_lines) if root_cause_lines else "No feature clearly outside normal training range."

    prompt = RAG_QUERY_PROMPT.format(
        name_machine=machine_name,
        top_shap=top_shap_term,
        root_cause=root_cause_text,
    )

    fallback_queries = [
        f"{machine_name} why {top_shap_term} can cause machine failure",
        f"{machine_name} troubleshooting machine failure caused by {top_shap_term}",
        f"{machine_name} components affected by {top_shap_term}",
        f"{machine_name} maintenance procedure for {top_shap_term}",
    ]

    try:
        import json

        raw = chat_json([{"role": "user", "content": prompt}])
        parsed = json.loads(raw)
        search_queries = [q for q in parsed.get("search_queries", []) if isinstance(q, str) and q.strip()]
        if not search_queries:
            raise ValueError("empty search_queries from LLM")
    except Exception:
        logger.exception("generate_search_queries: LLM query generation failed, using rule-based fallback")
        search_queries = fallback_queries

    return top_shap_term, search_queries
