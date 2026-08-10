import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMachine } from "../components/MachineContext.jsx";
import { api } from "../api/client.js";

function AddMachineModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [machineType, setMachineType] = useState("Haas");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { refreshMachines } = useMachine();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const machine = await api.createMachine({ name: name.trim(), machine_type: machineType.trim() || null });
      await refreshMachines();
      onCreated(machine.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ color: "var(--text)" }}>Tambah Mesin Baru</h3>
        <form onSubmit={handleSubmit} style={{ textAlign: "left" }}>
          <div className="field" style={{ marginBottom: 14 }}>
            <label>Nama Mesin</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="mis. Haas VF-2 Line B"
              required
              autoFocus
            />
          </div>
          <div className="field" style={{ marginBottom: 14 }}>
            <label>Tipe Mesin (opsional)</label>
            <input type="text" value={machineType} onChange={(e) => setMachineType(e.target.value)} placeholder="mis. Haas" />
          </div>
          {error && <div className="error-box">{error}</div>}
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn" type="submit" disabled={loading || !name.trim()}>
              {loading ? "Menyimpan..." : "Tambah Mesin"}
            </button>
            <button className="btn btn-secondary" type="button" onClick={onClose} disabled={loading}>
              Batal
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function MachineCard({ machine, onSelect }) {
  return (
    <div
      className="doc-card"
      role="button"
      tabIndex={0}
      onClick={() => onSelect(machine.id)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onSelect(machine.id)}
      title={`Pilih ${machine.name}`}
    >
      <svg viewBox="0 0 48 48" className="file-icon" aria-hidden="true" style={{ width: 56, height: 56 }}>
        <rect x="4" y="10" width="40" height="28" rx="3" fill="#e6e9f0" />
        <rect x="9" y="15" width="30" height="14" rx="2" fill="#3568e8" />
        <circle cx="14" cy="34" r="2.5" fill="#6b7385" />
        <circle cx="22" cy="34" r="2.5" fill="#6b7385" />
        <circle cx="30" cy="34" r="2.5" fill="#6b7385" />
      </svg>
      <div className="doc-card-name" title={machine.name}>
        {machine.name}
      </div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "center" }}>
        {machine.machine_type && <span className="badge badge-neutral">{machine.machine_type}</span>}
        <span className={`badge ${machine.status === "running" ? "badge-success" : "badge-neutral"}`}>
          {machine.status === "running" ? "Running" : machine.status}
        </span>
      </div>
      <div className="doc-card-meta">
        {machine.document_count} dokumen · {machine.run_count} run
      </div>
    </div>
  );
}

export default function MachineSelectPage() {
  const { machines, loading, error, selectMachine } = useMachine();
  const [showAddModal, setShowAddModal] = useState(false);
  const navigate = useNavigate();

  const handleSelect = (machineId) => {
    selectMachine(machineId);
    navigate("/dashboard");
  };

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: "1.3rem", margin: 0 }}>Pilih Mesin</h1>
        <p className="text-dim" style={{ marginTop: 6 }}>
          Pilih mesin yang ingin Anda monitor dan analisis, atau tambahkan mesin baru.
        </p>
      </div>

      {error && <div className="error-box">{error}</div>}

      <div className="card">
        <h2>
          Mesin Anda{" "}
          <button className="btn" style={{ float: "right", padding: "4px 12px" }} onClick={() => setShowAddModal(true)}>
            + Tambah Mesin
          </button>
        </h2>

        {loading ? (
          <div className="spinner" />
        ) : machines.length === 0 ? (
          <p className="text-dim">Belum ada mesin. Tambahkan mesin pertama Anda untuk mulai monitoring.</p>
        ) : (
          <div className="doc-grid">
            {machines.map((m) => (
              <MachineCard key={m.id} machine={m} onSelect={handleSelect} />
            ))}
          </div>
        )}
      </div>

      {showAddModal && (
        <AddMachineModal
          onClose={() => setShowAddModal(false)}
          onCreated={(machineId) => {
            setShowAddModal(false);
            handleSelect(machineId);
          }}
        />
      )}
    </div>
  );
}
