import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";
import { useMachine } from "../components/MachineContext.jsx";

export default function LoginPage({ onLoggedIn }) {
  const navigate = useNavigate();
  const { refreshMachines } = useMachine();
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [loginForm, setLoginForm] = useState({ username: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    username: "",
    email: "",
    password: "",
    full_name: "",
  });

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await api.login(loginForm.username, loginForm.password);
      localStorage.setItem("access_token", res.access_token);
      onLoggedIn();
      await refreshMachines();
      navigate("/machines", { replace: true });
    } catch (err) {
      setError(err.message || "Login gagal");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.register(registerForm);
      // Register tidak mengembalikan token (lihat routes_auth.py) — langsung
      // login pakai kredensial yang baru saja didaftarkan.
      const res = await api.login(registerForm.username, registerForm.password);
      localStorage.setItem("access_token", res.access_token);
      onLoggedIn();
      await refreshMachines();
      navigate("/machines", { replace: true });
    } catch (err) {
      setError(err.message || "Registrasi gagal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="card login-card">
        <h2>Predictive Maintenance Copilot</h2>
        <div className="toggle-group">
          <button
            className={`toggle-btn${mode === "login" ? " active" : ""}`}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
          >
            Login
          </button>
          <button
            className={`toggle-btn${mode === "register" ? " active" : ""}`}
            onClick={() => {
              setMode("register");
              setError(null);
            }}
          >
            Daftar
          </button>
        </div>

        {error && <div className="error-box">{error}</div>}

        {mode === "login" ? (
          <form className="login-form" onSubmit={handleLogin}>
            <div className="field">
              <label>Username</label>
              <input
                type="text"
                value={loginForm.username}
                onChange={(e) => setLoginForm((f) => ({ ...f, username: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={loginForm.password}
                onChange={(e) => setLoginForm((f) => ({ ...f, password: e.target.value }))}
                required
              />
            </div>
            <button className="btn" type="submit" disabled={loading}>
              {loading ? "Memproses..." : "Login"}
            </button>
          </form>
        ) : (
          <form className="login-form" onSubmit={handleRegister}>
            <div className="field">
              <label>Username</label>
              <input
                type="text"
                value={registerForm.username}
                onChange={(e) => setRegisterForm((f) => ({ ...f, username: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label>Email</label>
              <input
                type="email"
                value={registerForm.email}
                onChange={(e) => setRegisterForm((f) => ({ ...f, email: e.target.value }))}
                required
              />
            </div>
            <div className="field">
              <label>Nama Lengkap</label>
              <input
                type="text"
                value={registerForm.full_name}
                onChange={(e) => setRegisterForm((f) => ({ ...f, full_name: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={registerForm.password}
                onChange={(e) => setRegisterForm((f) => ({ ...f, password: e.target.value }))}
                required
                minLength={8}
              />
            </div>
            <button className="btn" type="submit" disabled={loading}>
              {loading ? "Memproses..." : "Daftar"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
