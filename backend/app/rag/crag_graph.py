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
    machine_id: str | None
    documents: list[RetrievedDocument]
    grade: Literal["relevant", "irrelevant"]
    used_web_fallback: bool
    answer: str
    part_name: str | None


RAG_ANSWER_PROMPT = """Anda adalah asisten teknis predictive maintenance untuk mesin CNC Haas.
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
    docs = retrieve_documents(state["query"], k=5, machine_id=state.get("machine_id"))
    return {**state, "documents": docs}


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


def run_crag(query_text: str, machine_id: str | None = None) -> CRAGState:
    """Entry point used by routes_report.py."""
    initial_state: CRAGState = {
        "query": query_text,
        "machine_id": machine_id,
        "documents": [],
        "grade": "irrelevant",
        "used_web_fallback": False,
        "answer": "",
        "part_name": None,
    }
    return crag_app.invoke(initial_state)


def _interpret_shap_feature(feature_name: str, value: float, feature_row: dict | None) -> str | None:
    """Terjemahkan satu fitur SHAP mentah ('Tool wear min'=220.0) jadi frasa bahasa
    Indonesia yang bisa dicari di knowledgebase ('pemakaian tool/alat sudah terlalu
    lama'), dibandingkan terhadap IQR bounds training model (best_performance_log.json)
    supaya "tinggi"/"lama" bukan klaim sembarangan — hanya dilabeli begitu nilainya
    benar-benar di luar rentang wajar data training.

    Returns None kalau nilainya masih dalam rentang wajar (fitur ini secara statistik
    tidak "tinggi"/"rendah" meski SHAP tetap menghitungnya berkontribusi — SHAP value
    bisa nonzero murni dari interaksi feature engineering, bukan berarti nilai fitur
    itu sendiri anomali).
    """
    from app.ml.predictor import get_model_bundle

    bundle = get_model_bundle()
    lower, upper = bundle.lower_bound, bundle.upper_bound

    if feature_name == "Tool wear min":
        hi = upper.get("Tool wear min")
        if hi is not None and value > hi:
            return f"pemakaian tool/alat potong sudah terlalu lama ({value:.0f} menit, melebihi batas wajar {hi:.0f} menit)"
        return None

    if feature_name == "Rotational speed rpm":
        lo, hi = lower.get("Rotational speed rpm"), upper.get("Rotational speed rpm")
        if hi is not None and value > hi:
            return f"kecepatan putar (rotational speed) terlalu tinggi ({value:.0f} rpm, melebihi batas wajar {hi:.0f} rpm)"
        if lo is not None and value < lo:
            return f"kecepatan putar (rotational speed) terlalu rendah ({value:.0f} rpm, di bawah batas wajar {lo:.0f} rpm)"
        return None

    if feature_name in ("Air temperature K", "Process temperature K") and feature_row:
        # temp_diff = Process - Air adalah fitur yang punya bounds, bukan suhu mentahnya
        # sendiri — dipakai sebagai proksi karena training bounds hanya menyimpan yang ini.
        temp_diff = feature_row.get("process_temperature_k", 0) - feature_row.get("air_temperature_k", 0)
        hi = upper.get("temp_diff")
        lo = lower.get("temp_diff")
        if hi is not None and temp_diff > hi:
            return f"selisih suhu proses terhadap suhu udara terlalu besar ({temp_diff:.1f} K, melebihi batas wajar {hi:.1f} K) — indikasi panas berlebih/heat dissipation bermasalah"
        if lo is not None and temp_diff < lo:
            return f"selisih suhu proses terhadap suhu udara terlalu kecil ({temp_diff:.1f} K, di bawah batas wajar {lo:.1f} K)"
        return None

    return None


def build_root_cause_query(shap_result: dict, predicted_label: bool, feature_row: dict | None = None) -> str:
    """Query yang dikirim ke retrieve — revisi rancangan.txt: BUKAN dump nilai sensor
    mentah ("Tool wear min=220.0, Air temperature K=304.5..."), melainkan interpretasi
    bahasa natural dari fitur SHAP yang paling mendorong prediksi ke arah failure
    (shap_value positif), supaya query-nya benar-benar deskriptif ("suhu terlalu
    tinggi", "pemakaian tool terlalu lama") dan lebih mudah menemukan chunk manual
    servis yang relevan lewat semantic search, dibanding query berisi angka mentah.
    """
    positive_features = [f for f in shap_result.get("features", []) if f["shap_value"] > 0]
    positive_features.sort(key=lambda f: f["shap_value"], reverse=True)

    interpretations = []
    for f in positive_features:
        phrase = _interpret_shap_feature(f["feature_name"], f["value"], feature_row)
        if phrase:
            interpretations.append(phrase)
        if len(interpretations) >= 3:
            break

    if interpretations:
        symptom_text = "; ".join(interpretations)
        return f"Penyebab dan solusi machine failure mesin CNC Haas akibat {symptom_text}."

    # Fallback: SHAP tidak menunjuk fitur yang benar-benar di luar rentang wajar
    # (jarang — prediksi failure tapi tak ada nilai sensor yang jelas anomali).
    top_names = ", ".join(f["feature_name"] for f in shap_result.get("features", [])[:3])
    return (
        f"Penyebab dan solusi machine failure mesin CNC Haas — faktor paling berpengaruh: {top_names}."
    )
