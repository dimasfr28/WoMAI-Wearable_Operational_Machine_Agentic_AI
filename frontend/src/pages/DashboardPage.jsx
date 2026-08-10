import React, { useCallback, useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api/client.js";
import { useMachine } from "../components/MachineContext.jsx";

// --- Gauges (inline SVG, no chart lib needed for these — recharts is used
// only for the sparklines below, which genuinely benefit from it) ---------

function CircularGauge({ value, max = 100, color, size = 92, strokeWidth = 9 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(1, value / max));
  const offset = circumference * (1 - pct);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--surface-2)"
        strokeWidth={strokeWidth}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: "stroke-dashoffset 0.4s ease" }}
      />
    </svg>
  );
}

// Half-circle (180deg) gauge — needle-less arc fill, like the reference's Failure Risk card.
function RadialGauge({ value, max = 100, color, size = 110, strokeWidth = 10 }) {
  const radius = (size - strokeWidth) / 2;
  const circumference = Math.PI * radius; // half circumference
  const pct = Math.max(0, Math.min(1, value / max));
  const offset = circumference * (1 - pct);
  const cy = size / 2 + 6;
  return (
    <svg width={size} height={size / 2 + strokeWidth} viewBox={`0 0 ${size} ${size / 2 + strokeWidth}`}>
      <path
        d={`M ${strokeWidth / 2} ${cy} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${cy}`}
        fill="none"
        stroke="var(--surface-2)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      <path
        d={`M ${strokeWidth / 2} ${cy} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${cy}`}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={offset}
        style={{ transition: "stroke-dashoffset 0.4s ease" }}
      />
    </svg>
  );
}

// Same half-circle shape as RadialGauge, reused for Prediction Stability with
// the reference's purple accent — kept as a distinct component name so each
// card's intent stays self-documenting at the call site.
function ArcGauge(props) {
  return <RadialGauge {...props} />;
}

function PulseIcon({ color }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2 12h4l2-7 4 14 3-9 2 5h5"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l10 18H2L12 3z"
        stroke="var(--warn)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <line x1="12" y1="10" x2="12" y2="14" stroke="var(--warn)" strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="17" r="1" fill="var(--warn)" />
    </svg>
  );
}

const PARAM_ICONS = {
  air_temperature_k: (color) => (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15V5a2 2 0 1 0-4 0v10a4 4 0 1 0 4 0z"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  ),
  process_temperature_k: (color) => (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15V5a2 2 0 1 0-4 0v10a4 4 0 1 0 4 0z"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  ),
  rotational_speed_rpm: (color) => (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke={color} strokeWidth="1.8" />
      <path d="M12 7v5l3 3" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  ),
  tool_wear_min: (color) => (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6 3h12M6 21h12M7 3c0 4 5 5 5 9s-5 5-5 9M17 3c0 4-5 5-5 9s5 5 5 9"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  ),
};

const CHART_PARAMS = [
  { key: "air_temperature_k", label: "Air Temperature", unit: "K", color: "#3b82f6" },
  { key: "process_temperature_k", label: "Process Temperature", unit: "K", color: "#22c55e" },
  { key: "rotational_speed_rpm", label: "Rotational Speed", unit: "rpm", color: "#f59e0b" },
  { key: "tool_wear_min", label: "Tool Wear", unit: "min", color: "#a855f7" },
];

// --- Summary cards ---------------------------------------------------------

function HealthScoreCard({ prediction }) {
  const score = prediction?.health_score;
  const label = score == null ? "—" : score >= 70 ? "Good Condition" : score >= 40 ? "Perlu Perhatian" : "Kondisi Buruk";
  const color = score == null ? "var(--text-dim)" : score >= 70 ? "var(--success)" : score >= 40 ? "var(--warn)" : "var(--danger)";
  return (
    <div className="card dash-card">
      <h2>Health Score</h2>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div style={{ position: "relative", width: 92, height: 92, flexShrink: 0 }}>
          <CircularGauge value={score ?? 0} color={color} />
          <div className="gauge-center-label">
            <div style={{ fontSize: "1.35rem", fontWeight: 700 }}>{score != null ? Math.round(score) : "—"}</div>
            <div style={{ fontSize: "0.7rem", color: "var(--text-dim)" }}>/100</div>
          </div>
        </div>
        <div>
          <div style={{ color, fontWeight: 600, fontSize: "0.92rem" }}>{label}</div>
          <p className="text-dim" style={{ margin: "6px 0 0", fontSize: "0.78rem" }}>
            AI Assessment
          </p>
          <p style={{ margin: "2px 0 0", fontSize: "0.8rem" }}>
            {score == null
              ? "Belum ada data prediksi."
              : score >= 70
                ? "Mesin dalam kondisi baik. Lanjutkan monitoring."
                : "Perlu perhatian lebih lanjut pada mesin ini."}
          </p>
        </div>
      </div>
    </div>
  );
}

function FailureRiskCard({ prediction }) {
  const risk = prediction ? prediction.failure_probability * 100 : null;
  const label = risk == null ? "—" : risk >= 70 ? "High Risk" : risk >= 30 ? "Medium Risk" : "Low Risk";
  const color = risk == null ? "var(--text-dim)" : risk >= 70 ? "var(--danger)" : risk >= 30 ? "var(--warn)" : "var(--success)";
  return (
    <div className="card dash-card">
      <h2>Failure Risk</h2>
      <div style={{ position: "relative", display: "inline-block" }}>
        <RadialGauge value={risk ?? 0} color={color} />
        <div className="gauge-center-label" style={{ top: "62%" }}>
          <div style={{ fontSize: "1.35rem", fontWeight: 700 }}>
            {risk != null ? risk.toFixed(0) : "—"}
            <span style={{ fontSize: "0.9rem" }}>%</span>
          </div>
        </div>
      </div>
      <div style={{ color, fontWeight: 600, fontSize: "0.88rem", marginTop: -2 }}>{label}</div>
    </div>
  );
}

function PredictionStabilityCard({ stabilityPct }) {
  const color = "var(--purple)";
  return (
    <div className="card dash-card">
      <h2>Prediction Stability</h2>
      <div style={{ position: "relative", display: "inline-block" }}>
        <ArcGauge value={stabilityPct ?? 0} color={color} />
        <div className="gauge-center-label" style={{ top: "62%" }}>
          <div style={{ fontSize: "1.35rem", fontWeight: 700 }}>{stabilityPct != null ? Math.round(stabilityPct) : "—"}%</div>
        </div>
      </div>
      <p className="text-dim" style={{ margin: "2px 0 0", fontSize: "0.78rem" }}>
        {stabilityPct == null ? "Belum ada data" : "Konsistensi 10 prediksi terakhir"}
      </p>
    </div>
  );
}

function StatusCard({ status }) {
  const s = status?.operational_status || "OFFLINE";
  const meta = {
    RUNNING: { color: "var(--success)", desc: "Normal Operation", sub: "No active alerts" },
    WARNING: { color: "var(--danger)", desc: "Failure Predicted", sub: "Perlu tindakan segera" },
    IDLE: { color: "var(--text-dim)", desc: "Idle", sub: "Menunggu data sensor baru" },
    OFFLINE: { color: "var(--text-dim)", desc: "Offline", sub: "Belum ada data sensor" },
  }[s];

  return (
    <div className="card dash-card">
      <h2>Status</h2>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <PulseIcon color={meta.color} />
        <span style={{ color: meta.color, fontWeight: 700, fontSize: "1.15rem" }}>{s}</span>
      </div>
      <p style={{ margin: "14px 0 0", fontSize: "0.85rem" }}>{meta.desc}</p>
      <p className="text-dim" style={{ margin: "2px 0 0" }}>
        {meta.sub}
      </p>
    </div>
  );
}

// --- Sensor Monitoring ------------------------------------------------------

function SensorSparkTooltip({ active, payload, param }) {
  if (!active || !payload || !payload.length) return null;
  const point = payload[0].payload;
  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "6px 10px",
        fontSize: "0.75rem",
        boxShadow: "0 4px 12px rgba(0,0,0,0.35)",
      }}
    >
      <div className="text-dim" style={{ marginBottom: 2 }}>
        {point.label}
      </div>
      <div style={{ fontWeight: 700, color: param.color }}>
        {point.value} {param.unit}
      </div>
    </div>
  );
}

function SensorRow({ param, points, stats }) {
  const data = points.map((p, i) => ({
    value: p[param.key],
    label: new Date(p.timestamp).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }),
    index: i + 1,
  }));
  return (
    <div className="sensor-row">
      <div className="sensor-row-icon" style={{ "--icon-bg": `${param.color}26` }}>
        {PARAM_ICONS[param.key](param.color)}
      </div>
      <div className="sensor-row-label">
        <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{param.label}</div>
        <div className="text-dim" style={{ fontSize: "0.72rem" }}>
          ({param.unit})
        </div>
      </div>
      <div className="sensor-row-value" style={{ color: param.color }}>
        {stats?.current != null ? stats.current : "—"} <span style={{ fontSize: "0.7rem", color: "var(--text-dim)" }}>{param.unit}</span>
      </div>
      <div className="sensor-row-spark">
        {data.length > 1 ? (
          <ResponsiveContainer width="100%" height={78}>
            <LineChart data={data} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fill: "var(--text-dim)", fontSize: 9 }}
                axisLine={{ stroke: "var(--border)" }}
                tickLine={false}
                minTickGap={20}
                height={16}
              />
              <YAxis
                domain={[stats?.min ?? "auto", stats?.max ?? "auto"]}
                tick={{ fill: "var(--text-dim)", fontSize: 9 }}
                axisLine={false}
                tickLine={false}
                width={34}
              />
              <Tooltip
                content={<SensorSparkTooltip param={param} />}
                cursor={{ stroke: "var(--text-dim)", strokeDasharray: "3 3" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={param.color}
                strokeWidth={2.5}
                dot={{ r: 3, fill: param.color, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: param.color, stroke: "var(--surface)", strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <span className="text-dim" style={{ fontSize: "0.75rem" }}>
            Belum cukup data
          </span>
        )}
      </div>
      <div className="sensor-row-stats text-dim">
        {stats && stats.min != null ? (
          <>
            <span>
              Min <strong style={{ color: "var(--text)" }}>{stats.min}</strong>
            </span>
            <span>
              Max <strong style={{ color: "var(--text)" }}>{stats.max}</strong>
            </span>
            <span>
              Avg <strong style={{ color: "var(--text)" }}>{stats.avg}</strong>
            </span>
          </>
        ) : (
          "—"
        )}
      </div>
    </div>
  );
}

function SensorMonitoringPanel({ history }) {
  const points = history?.points || [];
  const wear = points.map((p) => p.tool_wear_min);
  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        <h2 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <PulseIcon color="var(--accent)" /> Sensor Monitoring{" "}
          <span className="badge badge-success" style={{ marginLeft: 4 }}>
            Live Data
          </span>
        </h2>
        <p className="text-dim" style={{ margin: 0, fontSize: "0.8rem" }}>
          {history?.run_label ? (
            <>
              Run <strong style={{ color: "var(--text)" }}>{history.run_label}</strong>
              {wear.length > 0 && (
                <>
                  {" "}
                  · Tool Wear {wear[0]} → {wear[wear.length - 1]} min
                </>
              )}
            </>
          ) : (
            "Belum ada run"
          )}
        </p>
      </div>
      <div style={{ marginTop: 10 }}>
        {CHART_PARAMS.map((param) => (
          <SensorRow key={param.key} param={param} points={points} stats={history?.[param.key]} />
        ))}
      </div>
    </div>
  );
}

// --- AI Early Warning --------------------------------------------------------

// Urgensi = seberapa besar kontribusi SHAP parameter ini terhadap probabilitas
// failure saat ini (0-100, dijumlah ke total |SHAP| keempat parameter di
// backend). Skala warna hijau->kuning->oranye->merah mengikuti konvensi
// status yang sama dipakai di kartu Failure Risk.
function urgencyColor(pct) {
  if (pct >= 50) return "var(--danger)";
  if (pct >= 30) return "var(--warn)";
  if (pct >= 15) return "#eab308";
  return "var(--success)";
}

function urgencyBg(pct) {
  if (pct >= 50) return "var(--danger-bg)";
  if (pct >= 30) return "var(--warn-bg)";
  if (pct >= 15) return "rgba(234, 179, 8, 0.12)";
  return "var(--success-bg)";
}

function EarlyWarningItem({ item }) {
  const color = urgencyColor(item.shap_contribution_pct);
  const bg = urgencyBg(item.shap_contribution_pct);
  return (
    <div className="early-warning-box" style={{ background: bg, borderColor: color }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <p style={{ fontWeight: 600, color, margin: 0, fontSize: "0.88rem" }}>
          {item.parameter_label}{" "}
          <span className="text-dim" style={{ fontWeight: 400, fontSize: "0.78rem" }}>
            ({item.current_value} {item.unit})
          </span>
        </p>
        <span style={{ color, fontWeight: 700, fontSize: "0.74rem", whiteSpace: "nowrap" }}>
          {item.shap_contribution_pct.toFixed(0)}%
        </span>
      </div>
      <div className="upload-progress-track" style={{ marginTop: 6, height: 6 }}>
        <div className="upload-progress-fill" style={{ width: `${item.shap_contribution_pct}%`, background: color }} />
      </div>
      <p style={{ margin: "6px 0 0", fontSize: "0.8rem" }}>
        <span style={{ color, fontWeight: 600 }}>Rekomendasi: </span>
        {item.recommended_action}
      </p>
    </div>
  );
}

function AIEarlyWarningCard({ items }) {
  return (
    <div className="card">
      <h2 style={{ display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
        <WarningIcon /> AI Early Warning
      </h2>
      {!items || items.length === 0 ? (
        <p className="text-dim" style={{ marginTop: 14 }}>
          Tidak ada peringatan aktif — kondisi mesin dalam batas wajar.
        </p>
      ) : (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
          {items.map((item) => (
            <EarlyWarningItem key={item.parameter} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

// --- Page --------------------------------------------------------------------

export default function DashboardPage() {
  const { selectedMachineId, selectedMachine } = useMachine();
  const [history, setHistory] = useState(null);
  const [status, setStatus] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const loadAll = useCallback(async () => {
    if (!selectedMachineId) return;
    setLoading(true);
    setError(null);
    try {
      const [historyRes, statusRes] = await Promise.all([
        api.getSensorHistory(selectedMachineId),
        api.getMachineStatus(selectedMachineId),
      ]);
      setHistory(historyRes);
      setStatus(statusRes);
      try {
        const report = await api.getLatestReport(selectedMachineId);
        setPrediction(report.prediction);
      } catch {
        setPrediction(null);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedMachineId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  return (
    <div className="dashboard-page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 style={{ fontSize: "1.15rem", margin: 0 }}>Machine Overview</h1>
          <p className="text-dim" style={{ margin: "2px 0 0", fontSize: "0.82rem" }}>
            Real-time AI monitoring and health assessment
            {selectedMachine && (
              <>
                {" — "}
                <strong style={{ color: "var(--text)" }}>{selectedMachine.name}</strong>
              </>
            )}
          </p>
        </div>
        <button className="btn" onClick={loadAll} disabled={loading}>
          {loading ? "Memuat..." : "Refresh"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="dashboard-summary-grid">
        <HealthScoreCard prediction={prediction} />
        <FailureRiskCard prediction={prediction} />
        <PredictionStabilityCard stabilityPct={status?.prediction_stability_pct} />
        <StatusCard status={status} />
      </div>

      <div className="grid-2" style={{ alignItems: "start" }}>
        <SensorMonitoringPanel history={history} />
        <AIEarlyWarningCard items={status?.early_warning?.items} />
      </div>
    </div>
  );
}
