import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken } from "../api/client.js";

const STORAGE_KEY = "selected_machine_id";

const MachineContext = createContext(null);

export function MachineProvider({ children }) {
  const [machines, setMachines] = useState([]);
  const [selectedMachineId, setSelectedMachineIdState] = useState(() => localStorage.getItem(STORAGE_KEY));
  // Not loading until we actually know — GET /machines requires auth, so
  // there's nothing to fetch (and no point spinning) before a token exists.
  const [loading, setLoading] = useState(!!getToken());
  const [error, setError] = useState(null);

  const loadMachines = useCallback(async () => {
    if (!getToken()) {
      setMachines([]);
      setLoading(false);
      return [];
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.listMachines();
      setMachines(list);
      return list;
    } catch (err) {
      setError(err.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMachines();
  }, [loadMachines]);

  // If the persisted machine id no longer exists (deleted, or first run with
  // nothing selected yet), fall back to null rather than silently pointing at
  // a machine that's gone — MachineGate below sends the user back to the
  // selection page whenever selectedMachineId doesn't resolve to a real one.
  useEffect(() => {
    if (loading) return;
    if (selectedMachineId && !machines.some((m) => m.id === selectedMachineId)) {
      setSelectedMachineIdState(null);
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [loading, machines, selectedMachineId]);

  const selectMachine = useCallback((machineId) => {
    setSelectedMachineIdState(machineId);
    localStorage.setItem(STORAGE_KEY, machineId);
  }, []);

  const clearMachine = useCallback(() => {
    setSelectedMachineIdState(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const selectedMachine = machines.find((m) => m.id === selectedMachineId) || null;

  return (
    <MachineContext.Provider
      value={{
        machines,
        loading,
        error,
        selectedMachineId,
        selectedMachine,
        selectMachine,
        clearMachine,
        refreshMachines: loadMachines,
      }}
    >
      {children}
    </MachineContext.Provider>
  );
}

export function useMachine() {
  const ctx = useContext(MachineContext);
  if (!ctx) throw new Error("useMachine must be used inside <MachineProvider>");
  return ctx;
}
