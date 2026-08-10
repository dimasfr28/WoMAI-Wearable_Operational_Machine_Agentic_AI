const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function getToken() {
  return localStorage.getItem("access_token");
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail;
    try {
      detail = await res.json();
    } catch {
      detail = { detail: res.statusText };
    }
    // Token invalid/expired (or missing) mid-session: clear it and force the
    // user back to /login instead of leaving them stuck on a broken page.
    if (res.status === 401 && token) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
    }
    const err = new Error(typeof detail.detail === "string" ? detail.detail : JSON.stringify(detail.detail || detail));
    err.status = res.status;
    err.payload = detail;
    throw err;
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // auth
  login: (username, password) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  register: (payload) => request("/auth/register", { method: "POST", body: JSON.stringify(payload) }),

  // machines (multi-machine support: every domain endpoint below is scoped to
  // one machine via a machineId argument/query param)
  listMachines: () => request("/machines"),
  createMachine: (payload) => request("/machines", { method: "POST", body: JSON.stringify(payload) }),
  getMachine: (machineId) => request(`/machines/${machineId}`),
  getMachineStatus: (machineId) => request(`/machines/${machineId}/status`),

  // knowledgebase
  listDocuments: (machineId) => request(`/knowledgebase/documents?machine_id=${machineId}`),
  checkFilename: (filename, machineId) =>
    request(
      `/knowledgebase/upload/check-filename?filename=${encodeURIComponent(filename)}&machine_id=${machineId}`
    ),
  // XMLHttpRequest instead of fetch: fetch has no upload-progress event, and
  // the drive-style grid needs a per-file progress bar while MinerU parsing
  // is in flight (that's most of the wall-clock time here, not just the byte
  // transfer, but XHR's upload.onprogress is still the only signal we have).
  uploadPdf: (file, machineId, { replace = false, onProgress } = {}) => {
    const form = new FormData();
    form.append("file", file);
    const qs = new URLSearchParams({ machine_id: machineId, ...(replace ? { replace: "true" } : {}) });
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE_URL}/knowledgebase/upload/pdf?${qs.toString()}`);
      const token = getToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => {
        let payload;
        try {
          payload = JSON.parse(xhr.responseText);
        } catch {
          payload = { detail: xhr.statusText };
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(payload);
        } else {
          if (xhr.status === 401 && token) {
            localStorage.removeItem("access_token");
            window.location.href = "/login";
          }
          const err = new Error(
            typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload)
          );
          err.status = xhr.status;
          err.payload = payload;
          reject(err);
        }
      };
      xhr.onerror = () => reject(new Error("Koneksi ke server gagal"));
      xhr.send(form);
    });
  },
  deleteDocument: (id) => request(`/knowledgebase/documents/${id}`, { method: "DELETE" }),
  getDocumentChunks: (id) => request(`/knowledgebase/documents/${id}/chunks`),

  // sensor
  submitReading: (payload, machineId) =>
    request(`/sensor/readings?machine_id=${machineId}`, { method: "POST", body: JSON.stringify(payload) }),
  listRuns: (machineId) => request(`/sensor/runs?machine_id=${machineId}`),
  getSensorHistory: (machineId) =>
    request(`/sensor/readings/history?machine_id=${machineId}`),

  // report
  getLatestReport: (machineId) => request(`/report/latest?machine_id=${machineId}`),
  getReportHistory: (machineId) => request(`/report/history?machine_id=${machineId}`),
};

export { API_BASE_URL, getToken };
