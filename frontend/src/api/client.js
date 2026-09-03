/**
 * AI Growth Commerce API Client
 * Clean, promise-based API abstraction layer for all Storefront and Admin endpoints.
 */

const getApiBase = () => {
  if (typeof window !== 'undefined' && window.location) {
    if (window.location.port && window.location.port !== '8000') {
      return `http://${window.location.hostname || '127.0.0.1'}:8000`;
    }
  }
  return '';
};

const API_BASE = getApiBase();

// ─── In-flight request deduplication ─────────────────────────────────────────────
// If the same GET URL is requested while a previous fetch for it is in-flight,
// return the same promise instead of spawning a duplicate network request.
// This prevents React StrictMode, concurrent polls, and component remounts from
// hammering the backend with duplicate requests.
const _inFlight = new Map();

async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const method = (options.method || 'GET').toUpperCase();

  // Dedup only idempotent GET requests
  if (method === 'GET' && _inFlight.has(url)) {
    return _inFlight.get(url);
  }

  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  };

  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body);
  }

  const promise = (async () => {
    try {
      const res = await fetch(url, config);
      const contentType = res.headers.get('content-type');
      let data = null;
      if (contentType && contentType.includes('application/json')) {
        data = await res.json();
      } else {
        data = await res.text();
      }

      if (!res.ok) {
        const errorMsg = (data && data.detail) || (data && data.error) || (data && data.message) || `Request failed (${res.status})`;
        throw new Error(errorMsg);
      }
      return data;
    } catch (err) {
      console.error(`[API Error] ${method} ${endpoint}:`, err.message);
      throw err;
    } finally {
      // Clean up dedup cache after request settles
      if (method === 'GET') {
        _inFlight.delete(url);
      }
    }
  })();

  if (method === 'GET') {
    _inFlight.set(url, promise);
  }

  return promise;
}


export const api = {
  // --- USER & CATALOG ---
  getUserProfile: (userId = 'user_alex') => apiRequest(`/api/user?user_id=${encodeURIComponent(userId)}`),
  getInventory: (params = {}) => {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`/api/inventory${query ? `?${query}` : ''}`);
  },
  getProduct: (id) => apiRequest(`/api/inventory/${id}`),

  // --- CART ---
  getCart: (userId = 'user_alex') => apiRequest(`/api/cart?user_id=${encodeURIComponent(userId)}`),
  addToCart: (userId, productId, quantity = 1, size = null) => 
    apiRequest('/api/cart/add', {
      method: 'POST',
      body: { user_id: userId, product_id: productId, quantity, size }
    }),
  removeFromCart: (userId, productId, quantity = null) => 
    apiRequest('/api/cart/remove', {
      method: 'POST',
      body: { user_id: userId, product_id: productId, quantity }
    }),
  clearCart: (userId = 'user_alex') => 
    apiRequest(`/api/cart/clear?user_id=${encodeURIComponent(userId)}`, { method: 'POST' }),

  // --- ORDERS ---
  getOrders: (userId = null) => 
    apiRequest(userId ? `/api/orders?user_id=${encodeURIComponent(userId)}` : '/api/orders'),
  getOrderDetails: (orderId) => apiRequest(`/api/orders/${orderId}`),
  refundOrder: (orderId, reason = 'Customer Request') => 
    apiRequest(`/api/orders/${orderId}/refund?reason=${encodeURIComponent(reason)}`, { method: 'POST' }),

  // --- NOVA AI COPILOT ---
  chatWithNova: (prompt, userId = 'user_alex', conversationHistory = null) => 
    apiRequest('/api/chat', {
      method: 'POST',
      body: { prompt, user_id: userId, conversation_history: conversationHistory }
    }),

  // --- RAZORPAY & AP2 ---
  getPaymentConfig: () => apiRequest('/api/payment/config'),
  createRazorpayOrder: (userId = 'user_alex', currency = 'INR') => 
    apiRequest('/api/payment/create-order', {
      method: 'POST',
      body: { user_id: userId, currency }
    }),
  verifyRazorpayPayment: (payload) => 
    apiRequest('/api/payment/verify', {
      method: 'POST',
      body: payload
    }),
  updateRazorpayCredentials: (keyId, keySecret) => 
    apiRequest('/api/payment/credentials', {
      method: 'POST',
      body: { key_id: keyId, key_secret: keySecret }
    }),
  getAP2Status: (userId = 'user_alex') => 
    apiRequest(`/api/payment/ap2-status?user_id=${encodeURIComponent(userId)}`),
  agentAutonomousPay: (userId = 'user_alex', shippingAddress = null) => 
    apiRequest('/api/payment/agent-autopay', {
      method: 'POST',
      body: { user_id: userId, shipping_address: shippingAddress }
    }),

  // --- ADMIN COMMAND STUDIO ---
  getAdminOverview: () => apiRequest('/api/admin/overview'),
  getAdminAgentsStatus: () => apiRequest('/api/admin/agents/status'),
  triggerAdminAgent: (agentKey) => 
    apiRequest('/api/admin/agents/trigger', {
      method: 'POST',
      body: { agent_key: agentKey }
    }),
  updateAgentInterval: (agentKey, intervalSeconds) => 
    apiRequest('/api/admin/agents/interval', {
      method: 'POST',
      body: { agent_key: agentKey, interval_seconds: intervalSeconds }
    }),
  getAdminAgentLogs: (limit = 60) => apiRequest(`/api/admin/agent-logs?limit=${limit}`),
  getAdminAgentMessages: (limit = 60) => apiRequest(`/api/admin/agent-messages?limit=${limit}`),
  getAdminAgentConversations: (agentName = null, limit = 20) => 
    apiRequest(agentName ? `/api/admin/agent-conversations?agent_name=${encodeURIComponent(agentName)}&limit=${limit}` : `/api/admin/agent-conversations?limit=${limit}`),

  // Treasury & Wholesale Acquisition
  getAdminTreasury: (limit = 30) => apiRequest(`/api/admin/treasury?limit=${limit}`),
  acquireWholesaleStock: (productId, quantity = 20, actor = 'Store Owner') => 
    apiRequest('/api/admin/treasury/acquire-stock', {
      method: 'POST',
      body: { product_id: productId, quantity, actor }
    }),
  
  // Agent Salaries & Interactive Negotiation
  getAgentSalaries: () => apiRequest('/api/admin/salaries'),
  negotiateAgentSalary: (agentName, proposedSalary, rationale = 'Performance review') => 
    apiRequest('/api/admin/salaries/negotiate', {
      method: 'POST',
      body: { agent_name: agentName, proposed_salary: proposedSalary, rationale }
    }),
  payAgentSalaries: (agentName = null, actor = 'Store Owner') => 
    apiRequest('/api/admin/salaries/pay', {
      method: 'POST',
      body: { agent_name: agentName, actor }
    }),
  updateAgentSalary: (agentName, newSalary, status = 'Agreed') => 
    apiRequest('/api/admin/salaries/update', {
      method: 'POST',
      body: { agent_name: agentName, new_salary: newSalary, status }
    }),

  // AI Autonomous Shoppers
  getAIBuyers: () => apiRequest('/api/admin/buyers'),
  triggerAIBuyer: (buyerId = 'all') => 
    apiRequest('/api/admin/buyers/trigger', {
      method: 'POST',
      body: { buyer_id: buyerId }
    }),
  toggleAIBuyers: (enabled = null) => 
    apiRequest('/api/admin/buyers/toggle', {
      method: 'POST',
      body: { enabled }
    }),
  updateBuyerInterval: (buyerId = 'all', intervalSeconds = 60) =>
    apiRequest('/api/admin/buyers/interval', {
      method: 'POST',
      body: { buyer_id: buyerId, interval_seconds: intervalSeconds }
    }),


  // CEO Roundtable Discussion
  startCEODiscussion: (topic, participants = 'ALL_AGENTS') => 
    apiRequest('/api/admin/ceo/discussion', {
      method: 'POST',
      body: { topic, participants }
    }),

  // Inventory & Pricing Management
  adminUpdateInventory: (payload) => 
    apiRequest('/api/admin/inventory/update', {
      method: 'POST',
      body: payload
    }),
  adminAddProduct: (payload) => 
    apiRequest('/api/admin/inventory/add', {
      method: 'POST',
      body: payload
    }),
  adminBulkPrice: (category, percentage) => 
    apiRequest('/api/admin/inventory/bulk-price', {
      method: 'POST',
      body: { category, percentage }
    }),

  // Orders in Admin
  getAdminOrders: () => apiRequest('/api/admin/orders'),
  adminUpdateOrderStatus: (orderId, status, trackingNumber = null, notes = null) => 
    apiRequest(`/api/admin/orders/${orderId}/status`, {
      method: 'POST',
      body: { status, tracking_number: trackingNumber, notes }
    }),
  // Refunds
  refundOrder: (orderId, reason = 'Customer Request') => 
    apiRequest(`/api/orders/${encodeURIComponent(orderId)}/refund?reason=${encodeURIComponent(reason)}`, {
      method: 'POST'
    }),
  adminCancelOrder: (orderId, reason = 'Customer Request', forceOverride = false) => 
    apiRequest(`/api/admin/orders/${orderId}/cancel`, {
      method: 'POST',
      body: { reason, force_override: forceOverride }
    }),

  // Reviews
  adminGetReviews: () => apiRequest('/api/admin/reviews'),
  adminAddReview: (payload) => 
    apiRequest('/api/admin/reviews/add', {
      method: 'POST',
      body: payload
    }),
  adminGenerateReviewSummary: (productId) => 
    apiRequest('/api/admin/reviews/generate-summary', {
      method: 'POST',
      body: { product_id: productId }
    }),

  // CEO Direct Admin Chat
  adminChat: (prompt, conversationHistory = null) => 
    apiRequest('/api/admin/chat', {
      method: 'POST',
      body: { prompt, conversation_history: conversationHistory }
    }),

  // Reset Store to 0 Stock State
  resetStoreComplete: () => apiRequest('/api/admin/reset-store', { method: 'POST' }),

  // --- AGENT-TO-AGENT & AUTONOMOUS COMMERCE EXTENSIONS ---
  // Agent-Readable Catalog & Manifest

  getAgentCatalog: () => apiRequest('/.well-known/agent-catalog.json'),
  getAP2Manifest: () => apiRequest('/.well-known/ap2-manifest.json'),

  // Upsell & Cross-Sells
  getCartCrossSells: (userId = 'user_alex') => 
    apiRequest(`/api/cart/cross-sells?user_id=${encodeURIComponent(userId)}`),

  // Campaign Orchestrator
  getActiveCampaign: () => apiRequest('/api/campaigns/active'),
  getAdminCampaigns: () => apiRequest('/api/admin/campaigns'),
  launchAdminCampaign: (payload) => 
    apiRequest('/api/admin/campaigns/launch', {
      method: 'POST',
      body: payload
    }),
  activateAdminCampaign: (campaignId) =>
    apiRequest(`/api/admin/campaigns/${encodeURIComponent(campaignId)}/activate`, {
      method: 'POST'
    }),
  stopAdminCampaign: (campaignId) =>
    apiRequest(`/api/admin/campaigns/${encodeURIComponent(campaignId)}/stop`, {
      method: 'POST'
    }),
  deleteAdminCampaign: (campaignId) =>
    apiRequest(`/api/admin/campaigns/${encodeURIComponent(campaignId)}`, {
      method: 'DELETE'
    }),


  // Conversational In-App Checkout
  conversationalCheckout: (payload) => 
    apiRequest('/api/chat/conversational-checkout', {
      method: 'POST',
      body: payload
    }),

  // Explainable Audit Trail & Failure Simulation
  getAuditTrail: () => apiRequest('/api/admin/audit-trail'),
  simulateFailure: (failureType) => 
    apiRequest('/api/simulation/failure-test', {
      method: 'POST',
      body: { failure_type: failureType }
    })
};

