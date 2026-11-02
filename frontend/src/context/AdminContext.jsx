import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';

const AdminContext = createContext(null);

// How often to poll lightweight telemetry (ms)
const TELEMETRY_INTERVAL_MS = 2000;

export function AdminProvider({ children }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [runtime, setRuntime] = useState(null);
  const [connectionError, setConnectionError] = useState('');
  const [lastSync, setLastSync] = useState(null);
  const [overview, setOverview] = useState(null);
  const [agentsStatus, setAgentsStatus] = useState(null);
  const [treasury, setTreasury] = useState(null);
  const [salaries, setSalaries] = useState({});
  const [buyers, setBuyers] = useState([]);
  const [agentLogs, setAgentLogs] = useState([]);
  const [adminOrders, setAdminOrders] = useState([]);
  const [adminReviews, setAdminReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isScanningFleet, setIsScanningFleet] = useState(false);

  // Modals state
  const [isNegotiateModalOpen, setIsNegotiateModalOpen] = useState(false);
  const [negotiatingAgent, setNegotiatingAgent] = useState(null);
  const [isAddProductModalOpen, setIsAddProductModalOpen] = useState(false);
  const [isBulkPriceModalOpen, setIsBulkPriceModalOpen] = useState(false);
  const [isResetConfirmModalOpen, setIsResetConfirmModalOpen] = useState(false);

  // In-flight guards: prevent concurrent overlapping requests
  const telemetryInFlight = useRef(false);
  const fullLoadInFlight = useRef(false);

  // ─── Lightweight telemetry poll (fast-path: only reads in-memory state) ────────
  const fetchTelemetry = useCallback(async () => {
    if (telemetryInFlight.current) return;
    telemetryInFlight.current = true;
    try {
      const [runtimeData, logsData] = await Promise.all([api.getRuntime(), api.getAdminAgentLogs(80)]);
      setRuntime(runtimeData);
      setAgentsStatus(runtimeData.fleet);
      setAgentLogs(logsData.logs || []);
      setLastSync(new Date());
      setConnectionError('');
    } catch (error) {
      setConnectionError(error.message);
    } finally {
      telemetryInFlight.current = false;
    }
  }, []);

  // ─── Full data refresh (includes logs, orders, reviews, salaries) ───────────────
  const loadAllAdminData = useCallback(async () => {
    if (fullLoadInFlight.current) return;
    fullLoadInFlight.current = true;
    setIsLoading(true);
    try {
      // Run all requests in one parallel batch — no serial waterfall
      const [ovData, agData, trData, byData, salData, logsData, ordData, revData] = await Promise.all([
        api.getAdminOverview().catch(() => null),
        api.getRuntime().catch(() => null),
        api.getAdminTreasury(25).catch(() => null),
        api.getAIBuyers().catch(() => null),
        api.getAgentSalaries().catch(() => ({})),
        api.getAdminAgentLogs(80).catch(() => null),
        api.getAdminOrders().catch(() => ({ orders: [] })),
        api.adminGetReviews().catch(() => ({ reviews: [] }))
      ]);

      if (ovData) setOverview(ovData);
      if (agData) { setRuntime(agData); setAgentsStatus(agData.fleet); }
      if (trData) setTreasury(trData);
      if (byData?.buyers) setBuyers(byData.buyers);
      if (salData) setSalaries(salData);
      if (logsData?.logs) setAgentLogs(logsData.logs);
      if (ordData?.orders) setAdminOrders(ordData.orders);
      if (revData?.reviews) setAdminReviews(revData.reviews);
    } catch (e) {
      console.warn('[Admin] Full load error:', e.message);
    } finally {
      setIsLoading(false);
      fullLoadInFlight.current = false;
    }
  }, []);

  // ─── Periodic telemetry (fires when tab is visible; skips if in-flight) ─────────
  useEffect(() => {
    if (window.location.pathname.startsWith('/admin')) loadAllAdminData();

    const interval = setInterval(() => {
      // Only poll when the admin page is visible
      if (document.visibilityState === 'visible' && window.location.pathname.startsWith('/admin')) {
        fetchTelemetry();
      }
    }, TELEMETRY_INTERVAL_MS);
    const fullRefresh = setInterval(() => {
      if (document.visibilityState === 'visible' && window.location.pathname.startsWith('/admin')) loadAllAdminData();
    }, 10000);

    return () => { clearInterval(interval); clearInterval(fullRefresh); };
  }, [loadAllAdminData, fetchTelemetry]);

  // ─── Trigger single agent (fire-and-forget; poll after short delay) ──────────────
  const triggerAgent = useCallback(async (agentKey) => {
    try {
      const res = await api.triggerAdminAgent(agentKey);
      // Short delay — backend fires agent in background, then poll for updated status
      await fetchTelemetry();
      return res;
    } catch (e) {
      console.error(`[Admin] Failed to trigger agent ${agentKey}:`, e);
      throw e;
    }
  }, [fetchTelemetry]);

  // ─── Trigger all agents in parallel (not serial) ────────────────────────────────
  const triggerAllAgents = useCallback(async () => {
    setIsScanningFleet(true);
    const keys = ['price_manager', 'inventory_manager', 'order_manager', 'dispatcher', 'finance_manager', 'review_manager', 'ceo'];
    try {
      // Fire all in parallel — each returns immediately (fire-and-forget on backend)
      await Promise.all(keys.map(k => api.triggerAdminAgent(k)));
      // Poll for updated telemetry after a delay for agents to complete
      setTimeout(fetchTelemetry, 2000);
    } finally {
      setIsScanningFleet(false);
    }
  }, [fetchTelemetry]);

  return (
    <AdminContext.Provider value={{
      runtime, connectionError, lastSync,
      activeTab,
      setActiveTab,
      overview,
      agentsStatus,
      treasury,
      salaries,
      buyers,
      agentLogs,
      adminOrders,
      adminReviews,
      isLoading,
      isScanningFleet,
      loadAllAdminData,
      fetchTelemetry,
      triggerAgent,
      triggerAllAgents,
      // Modals
      isNegotiateModalOpen,
      setIsNegotiateModalOpen,
      negotiatingAgent,
      setNegotiatingAgent,
      isAddProductModalOpen,
      setIsAddProductModalOpen,
      isBulkPriceModalOpen,
      setIsBulkPriceModalOpen,
      isResetConfirmModalOpen,
      setIsResetConfirmModalOpen
    }}>
      {children}
    </AdminContext.Provider>
  );
}

export function useAdmin() {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error('useAdmin must be used within AdminProvider');
  return ctx;
}
