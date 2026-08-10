import React, { useEffect, useState, useCallback } from "react";
import { api } from "../api/client.js";
import { useMachine } from "../components/MachineContext.jsx";

function HealthFailureCards({ prediction }) {
  const healthScore = prediction.health_score;
  const failureRisk = prediction.failure_probability * 100;
  const healthLabel = healthScore >= 70 ? "Good Condition" : healthScore >= 40 ? "Perlu Perhatian" : "Kondisi Buruk";
  const riskLabel = failureRisk >= 70 ? "High Risk" : failureRisk >= 30 ? "Medium Risk" : "Low Risk";

  return (
    <div className="grid-2">
      <div className="card" style={{ textAlign: "center" }}>
        <h2>Health Score</h2>
        <div style={{ fontSize: "2.4rem", fontWeight: 700, color: "var(--success)" }}>
          {healthScore.toFixed(0)}
          <span style={{ fontSize: "1.2rem", color: "var(--text-dim)" }}>/100</span>
        </div>
        <p className="text-dim">{healthLabel}</p>
      </div>
      <div className="card" style={{ textAlign: "center" }}>
        <h2>Failure Risk</h2>
        <div
          style={{
            fontSize: "2.4rem",
            fontWeight: 700,
            color: prediction.predicted_label ? "var(--danger)" : "var(--success)",
          }}
        >
          {failureRisk.toFixed(1)}%
        </div>
        <p className="text-dim">
          {riskLabel} (threshold {(prediction.threshold * 100).toFixed(1)}%)
        </p>
      </div>
    </div>
  );
}

function SensorSummaryCard({ sensor, prediction }) {
  return (
    <div className="card">
      <h2>Sensor Terbaru</h2>
      <table>
        <tbody>
          <tr>
            <td>Air Temperature</td>
            <td>{sensor.air_temperature_k} K</td>
          </tr>
          <tr>
            <td>Process Temperature</td>
            <td>{sensor.process_temperature_k} K</td>
          </tr>
          <tr>
            <td>Rotational Speed</td>
            <td>{sensor.rotational_speed_rpm} rpm</td>
          </tr>
          <tr>
            <td>Tool Wear</td>
            <td>{sensor.tool_wear_min} min</td>
          </tr>
        </tbody>
      </table>
      <div style={{ marginTop: 16 }}>
        <span className={`badge ${prediction.predicted_label ? "badge-danger" : "badge-success"}`}>
          {prediction.predicted_label ? "FAILURE DIPREDIKSI" : "NORMAL"}
        </span>
        <span className="text-dim" style={{ marginLeft: 12 }}>
          probability: {(prediction.failure_probability * 100).toFixed(1)}% (threshold {(prediction.threshold * 100).toFixed(1)}%)
        </span>
      </div>
      <p className="text-dim">model: {prediction.model_version}</p>
    </div>
  );
}

function ShapChart({ shap }) {
  const maxAbs = Math.max(...shap.features.map((f) => Math.abs(f.shap_value)), 0.0001);
  return (
    <div className="card">
      <h2>SHAP — Fitur Paling Berpengaruh</h2>
      <p className="text-dim" style={{ marginTop: -8 }}>
        Kontribusi tiap fitur terhadap probabilitas kegagalan (poin persentase), relatif terhadap baseline
        model.
      </p>
      {shap.features.map((f) => {
        const barPct = (Math.abs(f.shap_value) / maxAbs) * 100;
        const contributionPct = f.shap_value * 100;
        const positive = f.shap_value >= 0;
        return (
          <div className="shap-bar-row" key={f.feature_name}>
            <span>{f.feature_name}</span>
            <div className="shap-bar-track">
              <div
                className={`shap-bar-fill ${positive ? "positive" : "negative"}`}
                style={{ width: `${barPct}%` }}
              />
            </div>
            <span className="text-dim">
              {positive ? "+" : ""}
              {contributionPct.toFixed(2)}%
            </span>
          </div>
        );
      })}
      <p className="text-dim">
        base value: {(shap.base_value * 100).toFixed(2)}% (probabilitas rata-rata sebelum melihat fitur spesifik ini)
      </p>
    </div>
  );
}

function WorstCaseCard({ delta }) {
  const adjustments = delta.suggested_adjustments || {};
  const entries = Object.entries(adjustments);
  return (
    <div className="card">
      <h2>Worst-Case Delta</h2>
      {entries.length === 0 ? (
        <p className="text-dim">Belum cukup data historis untuk menghitung rekomendasi.</p>
      ) : (
        <ul>
          {entries.map(([feature, value]) => (
            <li key={feature}>
              {feature}: {value >= 0 ? "+" : ""}
              {value} (menuju titik aman terdekat)
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function KnnCard({ recommendations }) {
  const rows = (group) => recommendations[group]?.rows || [];
  return (
    <div className="card">
      <h2>Kasus Serupa (KNN)</h2>
      <div className="grid-2">
        <div>
          <h3 style={{ fontSize: "0.9rem" }}>Nearest Failure</h3>
          <table>
            <thead>
              <tr>
                <th>Air T</th>
                <th>Proc T</th>
                <th>RPM</th>
                <th>Wear</th>
              </tr>
            </thead>
            <tbody>
              {rows("nearest_failure").map((r, i) => (
                <tr key={i}>
                  <td>{r.air_temperature_k}</td>
                  <td>{r.process_temperature_k}</td>
                  <td>{r.rotational_speed_rpm}</td>
                  <td>{r.tool_wear_min}</td>
                </tr>
              ))}
              {rows("nearest_failure").length === 0 && (
                <tr>
                  <td colSpan={4} className="text-dim">
                    tidak ada data
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div>
          <h3 style={{ fontSize: "0.9rem" }}>Nearest No-Failure</h3>
          <table>
            <thead>
              <tr>
                <th>Air T</th>
                <th>Proc T</th>
                <th>RPM</th>
                <th>Wear</th>
              </tr>
            </thead>
            <tbody>
              {rows("nearest_no_failure").map((r, i) => (
                <tr key={i}>
                  <td>{r.air_temperature_k}</td>
                  <td>{r.process_temperature_k}</td>
                  <td>{r.rotational_speed_rpm}</td>
                  <td>{r.tool_wear_min}</td>
                </tr>
              ))}
              {rows("nearest_no_failure").length === 0 && (
                <tr>
                  <td colSpan={4} className="text-dim">
                    tidak ada data
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function RootCauseCard({ rootCause }) {
  if (!rootCause) return null;
  const chunks = rootCause.retrieved_chunks || [];
  return (
    <div className="card">
      <h2>
        Root Cause Analysis
        <span className="source-badge">{rootCause.used_web_fallback ? "sumber: web (fallback)" : "sumber: knowledgebase"}</span>
      </h2>
      <p className="text-dim">query: {rootCause.query}</p>
      <div className="report-text">{rootCause.answer}</div>

      {chunks.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: "pointer", fontSize: "0.88rem", color: "var(--text-dim)" }}>
            {chunks.length} chunk knowledgebase dipakai untuk analisis ini
          </summary>
          <div style={{ marginTop: 10 }}>
            {chunks.map((c, i) => (
              <details className="chunk-item" key={c.chunk_id || i}>
                <summary>
                  #{i + 1} — {c.doc_name || "(sumber tidak diketahui)"}
                  {c.heading_2 ? ` / ${c.heading_2}` : c.heading_1 ? ` / ${c.heading_1}` : ""}
                </summary>
                <div className="chunk-content">{c.content}</div>
              </details>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function PartPriceCard({ partPrices }) {
  if (!partPrices || partPrices.length === 0) {
    return (
      <div className="card">
        <h2>Estimasi Harga Part</h2>
        <p className="text-dim">
          Tidak ada listing e-commerce yang ditemukan untuk part ini saat laporan dibuat (mesin pencari mungkin
          sedang tidak tersedia, atau part tidak dijual di platform yang dicek).
        </p>
      </div>
    );
  }
  return (
    <div className="card">
      <h2>Estimasi Harga Part</h2>
      <table>
        <thead>
          <tr>
            <th>Part</th>
            <th>Harga</th>
            <th>Sumber</th>
          </tr>
        </thead>
        <tbody>
          {partPrices.map((p, i) => (
            <tr key={i}>
              <td>{p.part_name}</td>
              <td>
                {p.price_min != null && p.price_max != null
                  ? p.price_min === p.price_max
                    ? `${p.currency} ${p.price_min.toLocaleString()}`
                    : `${p.currency} ${p.price_min.toLocaleString()} - ${p.price_max.toLocaleString()}`
                  : "tidak ditemukan"}
              </td>
              <td>
                {p.source_url ? (
                  <a href={p.source_url} target="_blank" rel="noreferrer">
                    link
                  </a>
                ) : (
                  "-"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FinalReportCard({ text, llmModel }) {
  return (
    <div className="card">
      <h2>Laporan Akhir</h2>
      <div className="report-text">{text}</div>
      <p className="text-dim" style={{ marginTop: 12 }}>
        model: {llmModel}
      </p>
    </div>
  );
}

export default function ReportPage() {
  const { selectedMachineId, selectedMachine } = useMachine();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadReport = useCallback(async () => {
    if (!selectedMachineId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getLatestReport(selectedMachineId);
      setReport(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedMachineId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: "1.3rem", margin: 0 }}>Report</h1>
          {selectedMachine && (
            <p className="text-dim" style={{ margin: "4px 0 0" }}>
              Mesin: <strong style={{ color: "var(--text)" }}>{selectedMachine.name}</strong>
            </p>
          )}
        </div>
        <button className="btn" onClick={loadReport} disabled={loading}>
          {loading ? "Memuat..." : "Refresh Report"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}
      {loading && !report && <div className="spinner" />}

      {report && (
        <>
          <HealthFailureCards prediction={report.prediction} />
          <div className="grid-2">
            <SensorSummaryCard sensor={report.sensor} prediction={report.prediction} />
            <ShapChart shap={report.shap} />
          </div>
          <div className="grid-2">
            <WorstCaseCard delta={report.recommendations.worst_case_delta} />
            <KnnCard recommendations={report.recommendations} />
          </div>
          <RootCauseCard rootCause={report.root_cause} />
          <PartPriceCard partPrices={report.part_prices} />
          <FinalReportCard text={report.final_report_text} llmModel={report.llm_model} />
        </>
      )}
    </div>
  );
}
