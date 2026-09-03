import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '../api/client';

const StoreContext = createContext(null);

export const USERS = [
  { id: 'user_alex', name: 'Alex Rivera', initials: 'AR', email: 'alex.rivera@growthcommerce.ai', address: '742 Evergreen Terrace, San Francisco, CA' },
  { id: 'user_sarah', name: 'Sarah Chen', initials: 'SC', email: 'sarah.chen@techventures.io', address: '102 Innovation Park, Silicon Hub, Bengaluru' }
];

// Polling interval for the storefront (8s is plenty — agent cycles run every 15-30s)
const STORE_POLL_INTERVAL_MS = 8000;

export function StoreProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(USERS[0]);
  const [catalog, setCatalog] = useState([]);
  const [cart, setCart] = useState({ items: [], item_count: 0, subtotal: 0, estimated_tax: 0, estimated_total: 0 });
  const [orders, setOrders] = useState([]);
  const [ap2Status, setAp2Status] = useState({ authorized: false, message: 'Loading...' });
  const [razorpayKey, setRazorpayKey] = useState('');
  const [isCartOpen, setIsCartOpen] = useState(false);
  const [isOrdersOpen, setIsOrdersOpen] = useState(false);
  const [isRzpModalOpen, setIsRzpModalOpen] = useState(false);
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [isLoadingCatalog, setIsLoadingCatalog] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  // In-flight guard for catalog/cart background polls
  const catalogInFlight = useRef(false);

  const showToast = useCallback((msg, type = 'info') => {
    setToastMessage({ msg, type });
    setTimeout(() => setToastMessage(null), 4000);
  }, []);

  // ─── Fetch catalog (with in-flight guard) ────────────────────────────────────────
  const refreshCatalog = useCallback(async () => {
    try {
      const data = await api.getInventory();
      setCatalog(data.products || []);
    } catch (e) {
      console.error('[Store] Failed to load catalog:', e.message);
    }
  }, []);

  // ─── Fetch cart ───────────────────────────────────────────────────────────────────
  const refreshCart = useCallback(async (userId = currentUser.id) => {
    try {
      const cartData = await api.getCart(userId);
      setCart(cartData || { items: [], item_count: 0, subtotal: 0, estimated_tax: 0, estimated_total: 0 });
    } catch (e) {
      console.error('[Store] Failed to load cart:', e.message);
    }
  }, [currentUser.id]);

  // ─── Fetch orders ─────────────────────────────────────────────────────────────────
  const refreshOrders = useCallback(async (userId = currentUser.id) => {
    try {
      const data = await api.getOrders(userId);
      setOrders(data.orders || []);
    } catch (e) {
      console.error('[Store] Failed to load orders:', e.message);
    }
  }, [currentUser.id]);

  // ─── Fetch AP2 status ─────────────────────────────────────────────────────────────
  const refreshAP2Status = useCallback(async (userId = currentUser.id) => {
    try {
      const data = await api.getAP2Status(userId);
      setAp2Status(data);
    } catch (e) {
      console.error('[Store] Failed to check AP2 status:', e.message);
    }
  }, [currentUser.id]);

  // ─── Fetch payment config ─────────────────────────────────────────────────────────
  const refreshPaymentConfig = useCallback(async () => {
    try {
      const cfg = await api.getPaymentConfig();
      setRazorpayKey(cfg.key_id || '');
    } catch (e) {
      console.error('[Store] Failed to get payment config:', e.message);
    }
  }, []);

  // ─── Switch user profile ──────────────────────────────────────────────────────────
  const switchUser = useCallback((user) => {
    setCurrentUser(user);
    setIsUserModalOpen(false);
    refreshCart(user.id);
    refreshOrders(user.id);
    refreshAP2Status(user.id);
    showToast(`Switched active profile to ${user.name}`, 'success');
  }, [refreshCart, refreshOrders, refreshAP2Status, showToast]);

  // ─── Add to cart ─────────────────────────────────────────────────────────────────
  const addToCart = useCallback(async (productId, size = null) => {
    try {
      const res = await api.addToCart(currentUser.id, productId, 1, size);
      if (res.cart) setCart(res.cart);
      showToast('Item added to cart!', 'success');
      return res;
    } catch (e) {
      showToast(e.message, 'error');
      throw e;
    }
  }, [currentUser.id, showToast]);

  // ─── Remove / decrement from cart ────────────────────────────────────────────────
  const removeFromCart = useCallback(async (productId, quantity = 1) => {
    try {
      const res = await api.removeFromCart(currentUser.id, productId, quantity);
      if (res.cart) setCart(res.cart);
      return res;
    } catch (e) {
      showToast(e.message, 'error');
      throw e;
    }
  }, [currentUser.id, showToast]);

  // ─── Initial load ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    setIsLoadingCatalog(true);
    Promise.all([
      refreshCatalog(),
      refreshCart(),
      refreshOrders(),
      refreshAP2Status(),
      refreshPaymentConfig()
    ]).finally(() => setIsLoadingCatalog(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Background catalog + cart sync (8s, in-flight safe, visibility-aware) ───────
  useEffect(() => {
    const timer = setInterval(async () => {
      // Skip when tab is hidden or poll already in-flight
      if (document.visibilityState !== 'visible') return;
      if (catalogInFlight.current) return;
      catalogInFlight.current = true;
      try {
        await Promise.all([refreshCatalog(), refreshCart()]);
      } finally {
        catalogInFlight.current = false;
      }
    }, STORE_POLL_INTERVAL_MS);

    return () => clearInterval(timer);
  }, [refreshCatalog, refreshCart]);

  return (
    <StoreContext.Provider value={{
      currentUser,
      switchUser,
      catalog,
      refreshCatalog,
      isLoadingCatalog,
      cart,
      refreshCart,
      addToCart,
      removeFromCart,
      orders,
      refreshOrders,
      ap2Status,
      refreshAP2Status,
      razorpayKey,
      refreshPaymentConfig,
      isCartOpen,
      setIsCartOpen,
      isOrdersOpen,
      setIsOrdersOpen,
      isRzpModalOpen,
      setIsRzpModalOpen,
      isUserModalOpen,
      setIsUserModalOpen,
      toastMessage,
      showToast
    }}>
      {children}
    </StoreContext.Provider>
  );
}

export function useStore() {
  const ctx = useContext(StoreContext);
  if (!ctx) throw new Error('useStore must be used within StoreProvider');
  return ctx;
}
