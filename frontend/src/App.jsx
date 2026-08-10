import React, { useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage.jsx";
import KnowledgebasePage from "./pages/KnowledgebasePage.jsx";
import ReportPage from "./pages/ReportPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import MachineSelectPage from "./pages/MachineSelectPage.jsx";
import { MachineProvider, useMachine } from "./components/MachineContext.jsx";
import { getToken } from "./api/client.js";

function RequireAuth({ isLoggedIn, children }) {
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return children;
}

// A machine must be selected before Knowledgebase/Report can be reached — both
// pages scope every request to selectedMachineId, so without one they'd have
// nothing valid to query.
function RequireMachine({ children }) {
  const { selectedMachineId, loading } = useMachine();
  if (loading) return <div className="spinner" />;
  if (!selectedMachineId) return <Navigate to="/machines" replace />;
  return children;
}

function MachineSwitcher() {
  const { machines, selectedMachineId, selectMachine } = useMachine();
  const navigate = useNavigate();

  if (machines.length === 0) return null;

  return (
    <select
      className="machine-switcher"
      value={selectedMachineId || ""}
      onChange={(e) => {
        if (e.target.value === "__add__") {
          navigate("/machines");
          return;
        }
        selectMachine(e.target.value);
      }}
    >
      <option value="" disabled>
        Pilih mesin...
      </option>
      {machines.map((m) => (
        <option key={m.id} value={m.id}>
          {m.name}
        </option>
      ))}
      <option value="__add__">+ Kelola mesin...</option>
    </select>
  );
}

function AppShell({ isLoggedIn, onLoggedIn, onLogout }) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">Predictive Maintenance Copilot</div>
        {isLoggedIn && (
          <>
            <nav className="app-nav">
              <NavLink to="/dashboard" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                Dashboard
              </NavLink>
              <NavLink to="/knowledgebase" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                Knowledgebase
              </NavLink>
              <NavLink to="/report" className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                Report
              </NavLink>
            </nav>
            <MachineSwitcher />
            <button className="btn btn-secondary" onClick={onLogout}>
              Logout
            </button>
          </>
        )}
      </header>
      <main className="app-main">
        <Routes>
          <Route
            path="/login"
            element={isLoggedIn ? <Navigate to="/machines" replace /> : <LoginPage onLoggedIn={onLoggedIn} />}
          />
          <Route path="/" element={<Navigate to={isLoggedIn ? "/machines" : "/login"} replace />} />
          <Route
            path="/machines"
            element={
              <RequireAuth isLoggedIn={isLoggedIn}>
                <MachineSelectPage />
              </RequireAuth>
            }
          />
          <Route
            path="/dashboard"
            element={
              <RequireAuth isLoggedIn={isLoggedIn}>
                <RequireMachine>
                  <DashboardPage />
                </RequireMachine>
              </RequireAuth>
            }
          />
          <Route
            path="/knowledgebase"
            element={
              <RequireAuth isLoggedIn={isLoggedIn}>
                <RequireMachine>
                  <KnowledgebasePage />
                </RequireMachine>
              </RequireAuth>
            }
          />
          <Route
            path="/report"
            element={
              <RequireAuth isLoggedIn={isLoggedIn}>
                <RequireMachine>
                  <ReportPage />
                </RequireMachine>
              </RequireAuth>
            }
          />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(() => !!getToken());

  const handleLogout = () => {
    localStorage.removeItem("access_token");
    setIsLoggedIn(false);
  };

  return (
    <BrowserRouter>
      <MachineProvider>
        <AppShell isLoggedIn={isLoggedIn} onLoggedIn={() => setIsLoggedIn(true)} onLogout={handleLogout} />
      </MachineProvider>
    </BrowserRouter>
  );
}
