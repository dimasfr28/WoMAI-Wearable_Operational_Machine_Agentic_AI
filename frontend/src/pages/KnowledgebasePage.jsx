import React, { useEffect, useState, useCallback, useRef } from "react";
import { api } from "../api/client.js";
import { useMachine } from "../components/MachineContext.jsx";

function ChunkTable({ chunks }) {
  if (!chunks || chunks.length === 0) return null;
  return (
    <div>
      {chunks.map((c, i) => (
        <details className="chunk-item" key={i}>
          <summary>
            #{c.chunk_index ?? i} — {c.heading_1 || "(tanpa heading 1)"} / {c.heading_2 || "(tanpa heading 2)"}
          </summary>
          <div className="chunk-content">{c.content}</div>
        </details>
      ))}
    </div>
  );
}

function ReplaceConfirmModal({ filename, onConfirm, onCancel }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ color: "var(--text)" }}>Ganti file?</h3>
        <p>
          File bernama <strong>{filename}</strong> sudah ada di knowledgebase. Ganti dengan file baru ini?
        </p>
        <p className="text-dim">Chunk &amp; embedding lama akan dihapus dan digantikan hasil dari file baru.</p>
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="btn" onClick={onConfirm}>
            Ganti
          </button>
          <button className="btn btn-secondary" onClick={onCancel}>
            Batal
          </button>
        </div>
      </div>
    </div>
  );
}

function FileIcon({ sourceType }) {
  // A plain PDF-page glyph for source_type="pdf"; a small grid glyph for
  // source_type="sensor_numeric" (CSV/sensor-derived documents have no PDF).
  if (sourceType === "pdf") {
    return (
      <svg viewBox="0 0 48 60" className="file-icon" aria-hidden="true">
        <path d="M6 2h24l12 12v44a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#e6e9f0" />
        <path d="M30 2l12 12H32a2 2 0 0 1-2-2V2z" fill="#c3c9d6" />
        <rect x="8" y="30" width="32" height="16" rx="2" fill="#e5534b" />
        <text x="24" y="41" textAnchor="middle" fontSize="11" fontWeight="700" fill="#fff">
          PDF
        </text>
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 48 60" className="file-icon" aria-hidden="true">
      <path d="M6 2h24l12 12v44a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#e6e9f0" />
      <path d="M30 2l12 12H32a2 2 0 0 1-2-2V2z" fill="#c3c9d6" />
      <rect x="8" y="30" width="32" height="16" rx="2" fill="#3ecf8e" />
      <text x="24" y="41" textAnchor="middle" fontSize="10" fontWeight="700" fill="#0f1420">
        CSV
      </text>
    </svg>
  );
}

function ChunksViewerModal({ doc, onClose }) {
  const [chunks, setChunks] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getDocumentChunks(doc.id)
      .then((res) => {
        if (!cancelled) setChunks(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [doc.id]);

  const handleDownload = () => {
    if (!chunks) return;
    const payload = chunks.map((c) => ({
      doc: doc.doc_name,
      machine_type: doc.machine_type,
      heading_1: c.heading_1,
      heading_2: c.heading_2,
      content: c.content,
    }));
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${doc.doc_name}.chunks.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ color: "var(--text)" }}>
          {doc.doc_name} <span className="text-dim" style={{ fontWeight: 400, fontSize: "0.8rem" }}>({doc.status})</span>
        </h3>

        {error && <div className="error-box">{error}</div>}

        {chunks === null && !error && <p className="text-dim">Memuat chunk...</p>}

        {chunks !== null && (
          <>
            <p className="text-dim" style={{ textAlign: "left", marginTop: -8 }}>
              {chunks.length} chunk
            </p>
            <div className="chunks-viewer-body">
              <ChunkTable chunks={chunks} />
            </div>
          </>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="btn btn-secondary" onClick={handleDownload} disabled={!chunks || chunks.length === 0}>
            Download JSON
          </button>
          <button className="btn btn-secondary" onClick={onClose}>
            Tutup
          </button>
        </div>
      </div>
    </div>
  );
}

function DeleteConfirmModal({ docName, onConfirm, onCancel, deleting }) {
  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Hapus dokumen?</h3>
        <p>
          <strong>{docName}</strong> dan seluruh chunk-nya akan dihapus permanen dari knowledgebase (Postgres + Chroma).
        </p>
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="btn btn-danger" onClick={onConfirm} disabled={deleting}>
            {deleting ? "Menghapus..." : "Hapus"}
          </button>
          <button className="btn btn-secondary" onClick={onCancel} disabled={deleting}>
            Batal
          </button>
        </div>
      </div>
    </div>
  );
}

function UploadCard({ upload }) {
  // upload: { id, name, progress (0-1), phase: "uploading" | "processing" | "error", error }
  const pct = Math.round((upload.progress || 0) * 100);
  return (
    <div className="doc-card doc-card-uploading" title={upload.name}>
      <FileIcon sourceType="pdf" />
      <div className="doc-card-name" title={upload.name}>
        {upload.name}
      </div>
      {upload.phase === "error" ? (
        <span className="badge badge-danger">gagal</span>
      ) : (
        <span className="badge badge-neutral">{upload.phase === "processing" ? "memproses..." : "mengunggah..."}</span>
      )}
      <div className="upload-progress-track">
        <div
          className={`upload-progress-fill${upload.phase === "processing" ? " indeterminate" : ""}`}
          style={upload.phase === "processing" ? undefined : { width: `${pct}%` }}
        />
      </div>
      {upload.phase === "error" ? (
        <div className="doc-card-meta upload-error-text" title={upload.error}>
          {upload.error}
        </div>
      ) : (
        <div className="doc-card-meta">{upload.phase === "processing" ? "parsing + embedding" : `${pct}%`}</div>
      )}
    </div>
  );
}

function DocumentsGrid({ documents, uploads, onRefresh, onFilesSelected }) {
  const [pendingDelete, setPendingDelete] = useState(null);
  const [viewingDoc, setViewingDoc] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteDocument(pendingDelete.id);
      setPendingDelete(null);
      onRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div
      className={`card dropzone-grid${dragOver ? " dragover" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        onFilesSelected(e.dataTransfer.files);
      }}
    >
      <h2>
        Dokumen Knowledgebase{" "}
        <span style={{ float: "right", display: "flex", gap: 8 }}>
          <button className="btn" style={{ padding: "4px 12px" }} onClick={() => fileInputRef.current?.click()}>
            + Upload PDF
          </button>
          <button className="btn btn-secondary" style={{ padding: "4px 12px" }} onClick={onRefresh}>
            Refresh
          </button>
        </span>
      </h2>
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        multiple
        style={{ display: "none" }}
        onChange={(e) => {
          onFilesSelected(e.target.files);
          e.target.value = "";
        }}
      />

      {error && <div className="error-box">{error}</div>}

      {dragOver && (
        <div className="dropzone-overlay">
          <p>Lepaskan file PDF di sini untuk mengunggah</p>
        </div>
      )}

      {documents.length === 0 && uploads.length === 0 ? (
        <p className="text-dim">Belum ada dokumen. Seret file PDF ke sini, atau klik "+ Upload PDF".</p>
      ) : (
        <div className="doc-grid">
          {uploads.map((u) => (
            <UploadCard key={u.id} upload={u} />
          ))}
          {documents.map((d) => (
            <div
              className="doc-card"
              key={d.id}
              role="button"
              tabIndex={0}
              title={d.chunk_count > 0 ? "Klik untuk lihat chunk" : "Belum ada chunk untuk ditampilkan"}
              onClick={() => d.chunk_count > 0 && setViewingDoc(d)}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && d.chunk_count > 0) setViewingDoc(d);
              }}
            >
              <button
                className="doc-card-delete"
                title="Hapus dokumen"
                onClick={(e) => {
                  e.stopPropagation();
                  setPendingDelete(d);
                }}
                aria-label={`Hapus ${d.doc_name}`}
              >
                ✕
              </button>
              <FileIcon sourceType={d.source_type} />
              <div className="doc-card-name" title={d.doc_name}>
                {d.doc_name}
              </div>
              <span
                className={`badge ${
                  d.status === "completed"
                    ? "badge-success"
                    : d.status === "failed" || d.status === "rejected_duplicate"
                      ? "badge-danger"
                      : "badge-neutral"
                }`}
              >
                {d.status}
              </span>
              <div className="doc-card-meta">
                {d.chunk_count} chunk · {new Date(d.uploaded_at).toLocaleDateString()}
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingDelete && (
        <DeleteConfirmModal
          docName={pendingDelete.doc_name}
          deleting={deleting}
          onConfirm={handleDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {viewingDoc && <ChunksViewerModal doc={viewingDoc} onClose={() => setViewingDoc(null)} />}
    </div>
  );
}

let uploadIdSeq = 0;

export default function KnowledgebasePage() {
  const { selectedMachineId, selectedMachine } = useMachine();
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState(null);
  const [uploads, setUploads] = useState([]);
  const [replaceQueue, setReplaceQueue] = useState([]); // files pending a replace-confirm decision

  const loadDocuments = useCallback(async () => {
    if (!selectedMachineId) return;
    try {
      const docs = await api.listDocuments(selectedMachineId);
      setDocuments(docs);
    } catch (err) {
      setError(err.message);
    }
  }, [selectedMachineId]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const runUpload = useCallback(
    async (file, { replace = false } = {}) => {
      const id = ++uploadIdSeq;
      setUploads((prev) => [...prev, { id, name: file.name, progress: 0, phase: "uploading" }]);
      try {
        await api.uploadPdf(file, selectedMachineId, {
          replace,
          onProgress: (p) => {
            setUploads((prev) =>
              prev.map((u) => (u.id === id ? { ...u, progress: p, phase: p >= 1 ? "processing" : "uploading" } : u))
            );
          },
        });
        setUploads((prev) => prev.filter((u) => u.id !== id));
        loadDocuments();
      } catch (err) {
        if (err.status === 409 && err.payload?.detail?.error === "filename_exists") {
          setUploads((prev) => prev.filter((u) => u.id !== id));
          setReplaceQueue((prev) => [...prev, file]);
          return;
        }
        const message =
          err.status === 422 && err.payload?.detail?.error === "duplicate_content"
            ? `Konten sudah ada di knowledgebase (${err.payload.detail.reason})`
            : err.message;
        setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, phase: "error", error: message } : u)));
        setTimeout(() => setUploads((prev) => prev.filter((u) => u.id !== id)), 6000);
      }
    },
    [loadDocuments, selectedMachineId]
  );

  const handleFilesSelected = useCallback(
    (fileList) => {
      const files = Array.from(fileList || []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
      for (const file of files) {
        runUpload(file);
      }
    },
    [runUpload]
  );

  const currentReplaceFile = replaceQueue[0] || null;

  return (
    <div>
      {selectedMachine && (
        <p className="text-dim" style={{ marginTop: -8, marginBottom: 16 }}>
          Mesin: <strong style={{ color: "var(--text)" }}>{selectedMachine.name}</strong>
        </p>
      )}

      {error && <div className="error-box">{error}</div>}

      <DocumentsGrid documents={documents} uploads={uploads} onRefresh={loadDocuments} onFilesSelected={handleFilesSelected} />

      {currentReplaceFile && (
        <ReplaceConfirmModal
          filename={currentReplaceFile.name}
          onConfirm={() => {
            setReplaceQueue((prev) => prev.slice(1));
            runUpload(currentReplaceFile, { replace: true });
          }}
          onCancel={() => setReplaceQueue((prev) => prev.slice(1))}
        />
      )}
    </div>
  );
}
