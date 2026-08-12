"""RAG — Arsitektur CRAG dengan LangGraph — Section 6.9.

Dipanggil langsung (sinkron) oleh routes_report.py (Section 6.11) hanya ketika
predicted_label = True. BUKAN tool agent chatbot (chatbot belum dibangun fase
ini) — signature-nya tetap tool-ready untuk dipakai ulang nanti.
"""
from __future__ import annotations

import logging
from typing import Literal, TypedDict

from langgraph.graph import StateGraph, END

from app.llm.groq_client import chat, chat_json
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


RAG_ANSWER_PROMPT = """Anda adalah asisten teknis predictive maintenance untuk mesin CNC.
Berdasarkan konteks di bawah (manual servis / troubleshooting guide / riwayat data sensor),
jawab query berikut dalam Bahasa Indonesia dengan TEPAT tiga bagian berikut, masing-masing
sebagai heading terpisah:

## Apa Masalahnya
Diagnosis singkat: kondisi/kegagalan apa yang kemungkinan terjadi berdasarkan konteks dan data sensor.

## SOP Penanganan
Langkah-langkah konkret dan actionable yang harus dilakukan teknisi untuk mengatasi masalah ini,
mengacu pada prosedur di konteks (manual servis/troubleshooting guide) bila tersedia.

## Part/Komponen Bermasalah
Part atau komponen SPESIFIK yang paling mungkin perlu diperiksa/diganti — sebutkan nama
komponen teknis yang konkret dan bisa dicari harganya di marketplace (mis. "spindle bearing",
"ballscrew", "coolant pump", "servo motor axis Z", "toolholder"), BUKAN istilah generik
seperti "Tool" atau "Gearbox" saja tanpa detail. Kalau konteks menyebut part number/kode
spesifik, sertakan itu juga.

Query: {query}

Konteks:
{context}

Di akhir jawaban, sertakan baris terpisah dengan format persis (harus sama dengan nama part
yang disebut di bagian "Part/Komponen Bermasalah" di atas):
PART_NAME: <nama part/komponen yang paling mungkin perlu diganti/diperiksa, atau "tidak diketahui">
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


def _extract_part_name(answer_text: str) -> str | None:
    for line in answer_text.splitlines():
        if line.strip().upper().startswith("PART_NAME:"):
            value = line.split(":", 1)[1].strip()
            if value and value.lower() != "tidak diketahui":
                return value
    return None


MAX_CHUNK_CHARS_IN_PROMPT = 800


def generate_answer(state: CRAGState) -> CRAGState:
    # Bug ditemukan lewat testing nyata: tanpa batas ini, 8 chunk (5 dari
    # knowledgebase_docs + 3 dari knowledgebase_sensor_runs) bisa total >30K
    # karakter (~9K+ token) — melebihi TPM 12000/menit Groq free tier begitu
    # ditambah prompt instruksi + jawaban, request ditolak 413 dan seluruh
    # analisis root cause jatuh ke fallback. grade_documents (grader.py) sudah
    # membatasi ke 800 char/dok untuk alasan yang sama; disamakan di sini.
    context = (
        "\n\n".join(d.page_content[:MAX_CHUNK_CHARS_IN_PROMPT] for d in state["documents"])
        or "(tidak ada konteks ditemukan)"
    )
    prompt = RAG_ANSWER_PROMPT.format(query=state["query"], context=context)
    try:
        answer = chat([{"role": "user", "content": prompt}])
    except Exception:
        logger.exception("generate_answer: Groq call failed")
        answer = (
            "Tidak dapat menghasilkan analisis root cause otomatis saat ini "
            "(layanan LLM tidak tersedia). Silakan periksa manual servis terkait secara manual.\n"
            "PART_NAME: tidak diketahui"
        )
    part_name = _extract_part_name(answer)
    return {**state, "answer": answer, "part_name": part_name}


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
    }
    return crag_app.invoke(initial_state)


# Mapping mentah -> istilah umum, dipakai untuk mengisi [TOP SHAP] di
# RAG_QUERY_PROMPT — persis daftar "VARIABLE NORMALIZATION" di rancangan.txt.
# LLM sendiri juga diinstruksikan melakukan normalisasi yang sama, tapi
# mengisi placeholder dengan istilah yang SUDAH dinormalisasi di sini membuat
# perilakunya tidak bergantung penuh pada LLM mematuhi instruksi normalisasi
# — kalau LLM lupa/salah, [TOP SHAP] yang disubstitusi tetap benar.
_SHAP_FEATURE_TO_GENERAL_TERM = {
    "Air temperature K": "heat / temperature",
    "Process temperature K": "heat / temperature",
    "Rotational speed rpm": "speed",
    "Tool wear min": "machine operating time",
}


def _is_feature_anomalous(feature_name: str, value: float, feature_row: dict | None) -> bool:
    """True kalau nilai fitur ini benar-benar di luar IQR bounds training
    model (best_performance_log.json) — dipakai untuk MEMILIH top-SHAP mana
    yang genuinely anomali (bukan cuma "paling berkontribusi" tapi nilainya
    masih dalam rentang wajar; SHAP value bisa nonzero murni dari interaksi
    feature engineering)."""
    from app.ml.predictor import get_model_bundle

    bundle = get_model_bundle()
    lower, upper = bundle.lower_bound, bundle.upper_bound

    if feature_name == "Tool wear min":
        hi = upper.get("Tool wear min")
        return hi is not None and value > hi

    if feature_name == "Rotational speed rpm":
        lo, hi = lower.get("Rotational speed rpm"), upper.get("Rotational speed rpm")
        return (hi is not None and value > hi) or (lo is not None and value < lo)

    if feature_name in ("Air temperature K", "Process temperature K") and feature_row:
        temp_diff = feature_row.get("process_temperature_k", 0) - feature_row.get("air_temperature_k", 0)
        hi, lo = upper.get("temp_diff"), lower.get("temp_diff")
        return (hi is not None and temp_diff > hi) or (lo is not None and temp_diff < lo)

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
    shap_result: dict, machine_name: str = "CNC machine", feature_row: dict | None = None
) -> tuple[str, list[str]]:
    """Query generation via LLM (rancangan.txt's RAG_QUERY_PROMPT) — mengganti
    build_root_cause_query()/_interpret_shap_feature() rule-based sebelumnya.
    Query sekarang ADAPTIF: LLM men-generate beberapa query bahasa Inggris
    (cause/troubleshooting/component/maintenance) dari deskripsi root-cause,
    bukan template kalimat hardcode per nama fitur.

    Root-cause description yang dikirim ke LLM tetap dibangun dari IQR bounds
    (_is_feature_anomalous) — bukan LLM yang menilai "apakah nilainya tinggi",
    supaya klaim anomali tetap berbasis statistik training data, bukan
    tebakan LLM. LLM hanya bertugas mengubah gejala itu jadi query pencarian
    yang adaptif dan general (tidak hardcode nama part/istilah dataset).

    Returns (top_shap_term, search_queries) — top_shap_term dipakai sebagai
    representasi ringkas untuk RootCauseAnalysis.rag_query (kolom tunggal di
    DB), search_queries dipakai retrieve() untuk multi-query retrieval.
    """
    features = sorted(shap_result.get("features", []), key=lambda f: f["shap_value"], reverse=True)
    anomalous = [f for f in features if f["shap_value"] > 0 and _is_feature_anomalous(f["feature_name"], f["value"], feature_row)]

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
