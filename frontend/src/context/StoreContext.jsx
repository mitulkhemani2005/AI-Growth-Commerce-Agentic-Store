import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

const StoreContext = createContext(null);

export const USERS = [
  { id: 'user_alex', name: 'Alex Rivera', initials: 'AR', email: 'alex.rivera@growthcommerce.ai', address: '742 Evergreen Terrace, San Francisco, CA' },
  { id: 'user_sarah', name: 'Sarah Chen', initials: 'SC', email: 'sarah.chen@techventures.io', address: '102 Innovation Park, Silicon Hub, Bengaluru' }
];

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

  const showToast = useCallback((msg, type = 'info') => {
    setToastMessage({ msg, type });
    setTimeout(() => setToastMessage(null), 4000);
  }, []);

  // Fetch catalog
  const refreshCatalog = useCallback(async () => {
    try {
      const data = await api.getInventory();
      setCatalog(data.products || []);
    } catch (e) {
      console.error('Failed to load catalog:', e);
    }
  }, []);

  // Fetch cart
  const refreshCart = useCallback(async (userId = currentUser.id) => {
    try {
      const cartData = await api.getCart(userId);
      setCart(cartData || { items: [], item_count: 0, subtotal: 0, estimated_tax: 0, estimated_total: 0 });
    } catch (e) {
      console.error('Failed to load cart:', e);
    }
  }, [currentUser.id]);

  // Fetch orders
  const refreshOrders = useCallback(async (userId = currentUser.id) => {
    try {
      const data = await api.getOrders(userId);
      setOrders(data.orders || []);
    } catch (e) {
      console.error('Failed to load orders:', e);
    }
  }, [currentUser.id]);

  // Fetch AP2 status
  const refreshAP2Status = useCallback(async (userId = currentUser.id) => {
    try {
      const data = await api.getAP2Status(userId);
      setAp2Status(data);
    } catch (e) {
      console.error('Failed to check AP2 status:', e);
    }
  }, [currentUser.id]);

  // Fetch payment config
  const refreshPaymentConfig = useCallback(async () => {
    try {
      const cfg = await api.getPaymentConfig();
      setRazorpayKey(cfg.key_id || '');
    } catch (e) {
      console.error('Failed to get payment config:', e);
    }
  }, []);

  // Switch user profile
  const switchUser = useCallback((user) => {
    setCurrentUser(user);
    setIsUserModalOpen(false);
    refreshCart(user.id);
    refreshOrders(user.id);
    refreshAP2Status(user.id);
    showToast(`Switched active profile to ${user.name}`, 'success');
  }, [refreshCart, refreshOrders, refreshAP2Status, showToast]);

  // Add to cart
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

  // Remove / decrement from cart
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

  // Initial load and periodic catalog polling
  useEffect(() => {
    setIsLoadingCatalog(true);
    Promise.all([
      refreshCatalog(),
      refreshCart(),
      refreshOrders(),
      refreshAP2Status(),
      refreshPaymentConfig()
    ]).finally(() => setIsLoadingCatalog(false));

    // Periodic sync every 4s to catch real-time agent price optimizations & buyer acquisitions
    const timer = setInterval(() => {
      refreshCatalog();
      refreshCart();
    }, 4000);

    return () => clearInterval(timer);
  }, [refreshCatalog, refreshCart, refreshOrders, refreshAP2Status, refreshPaymentConfig]);

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
