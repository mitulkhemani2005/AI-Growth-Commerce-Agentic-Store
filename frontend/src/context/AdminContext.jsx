import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

const AdminContext = createContext(null);

export function AdminProvider({ children }) {
  const [activeTab, setActiveTab] = useState('overview');
  const [overview, setOverview] = useState(null);
  const [agentsStatus, setAgentsStatus] = useState(null);
  const [treasury, setTreasury] = useState(null);
  const [salaries, setSalaries] = useState({});
  const [buyers, setBuyers] = useState([]);
  const [agentLogs, setAgentLogs] = useState([]);
  const [agentMessages, setAgentMessages] = useState([]);
  const [adminOrders, setAdminOrders] = useState([]);
  const [adminReviews, setAdminReviews] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isScanningFleet, setIsScanningFleet] = useState(false);

  // Modals state
  const [isAcquireModalOpen, setIsAcquireModalOpen] = useState(false);
  const [isNegotiateModalOpen, setIsNegotiateModalOpen] = useState(false);
  const [negotiatingAgent, setNegotiatingAgent] = useState(null);
  const [isAddProductModalOpen, setIsAddProductModalOpen] = useState(false);
  const [isBulkPriceModalOpen, setIsBulkPriceModalOpen] = useState(false);
  const [isResetConfirmModalOpen, setIsResetConfirmModalOpen] = useState(false);

  // Poll lightweight telemetry every 2.5 seconds
  const fetchTelemetry = useCallback(async () => {
    try {
      const [ovData, agData, trData, byData, msgData] = await Promise.all([
        api.getAdminOverview().catch(() => null),
        api.getAdminAgentsStatus().catch(() => null),
        api.getAdminTreasury(25).catch(() => null),
        api.getAIBuyers().catch(() => null),
        api.getAdminAgentMessages(30).catch(() => null)
      ]);

      if (ovData) setOverview(ovData);
      if (agData) setAgentsStatus(agData);
      if (trData) setTreasury(trData);
      if (byData && byData.buyers) setBuyers(byData.buyers);
      if (msgData && msgData.messages) setAgentMessages(msgData.messages);
    } catch (e) {
      console.warn('Telemetry poll error:', e);
    }
  }, []);

  // Full data refresh on tab change or explicit refresh
  const loadAllAdminData = useCallback(async () => {
    setIsLoading(true);
    try {
      await fetchTelemetry();
      const [salData, logsData, ordData, revData] = await Promise.all([
        api.getAgentSalaries().catch(() => ({})),
        api.getAdminAgentLogs(50).catch(() => ({ logs: [] })),
        api.getAdminOrders().catch(() => ({ orders: [] })),
        api.adminGetReviews().catch(() => ({ reviews: [] }))
      ]);

      if (salData) setSalaries(salData);
      if (logsData && logsData.logs) setAgentLogs(logsData.logs);
      if (ordData && ordData.orders) setAdminOrders(ordData.orders);
      if (revData && revData.reviews) setAdminReviews(revData.reviews);
    } finally {
      setIsLoading(false);
    }
  }, [fetchTelemetry]);

  // Initial load & interval timer
  useEffect(() => {
    loadAllAdminData();
    const interval = setInterval(fetchTelemetry, 2500);
    return () => clearInterval(interval);
  }, [loadAllAdminData, fetchTelemetry]);

  // Trigger single agent scan
  const triggerAgent = async (agentKey) => {
    try {
      const res = await api.triggerAdminAgent(agentKey);
      await fetchTelemetry();
      return res;
    } catch (e) {
      console.error(`Failed to trigger agent ${agentKey}:`, e);
      throw e;
    }
  };

  // Trigger all agents in sequence
  const triggerAllAgents = async () => {
    setIsScanningFleet(true);
    const keys = ['price_manager', 'inventory_manager', 'order_manager', 'dispatcher', 'finance_manager', 'review_manager', 'ceo'];
    try {
      for (const k of keys) {
        await api.triggerAdminAgent(k).catch(() => null);
      }
      await loadAllAdminData();
    } finally {
      setIsScanningFleet(false);
    }
  };

  return (
    <AdminContext.Provider value={{
      activeTab,
      setActiveTab,
      overview,
      agentsStatus,
      treasury,
      salaries,
      buyers,
      agentLogs,
      agentMessages,
      adminOrders,
      adminReviews,
      isLoading,
      isScanningFleet,
      loadAllAdminData,
      fetchTelemetry,
      triggerAgent,
      triggerAllAgents,
      // Modals
      isAcquireModalOpen,
      setIsAcquireModalOpen,
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
