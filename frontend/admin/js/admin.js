// Admin Dashboard State & Logic
let currentTab = 'overview';
let cachedProducts = [];
let cachedOrders = [];
let cachedReviews = [];
let cachedAgents = {};
let telemetryPollingInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) window.lucide.createIcons();
  setupNavigation();
  setupEventListeners();
  loadAllAdminData();
  
  // Live background telemetry poll (every 2s) — updates status counters & message bus in real-time
  telemetryPollingInterval = setInterval(pollTelemetryData, 2000);
});

function setupNavigation() {
  const navButtons = document.querySelectorAll('.nav-item');
  navButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      switchTab(tab);
    });
  });
}

function switchTab(tabName) {
  currentTab = tabName;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

  const activeBtn = document.querySelector(`.nav-item[data-tab="${tabName}"]`);
  const activePane = document.getElementById(`tab-${tabName}`);
  if (activeBtn) activeBtn.classList.add('active');
  if (activePane) activePane.classList.add('active');

  const titles = {
    overview: { title: 'Store Overview', sub: 'Real-time telemetry, automated agent actions, and store health (INR ₹, 0% Tax)' },
    agents: { title: '24/7 Autonomous Agent Fleet', sub: '7 Autonomous agents collaborating in real time via Inter-Agent Message Bus' },
    orders: { title: 'Orders & Dispatch Pipeline', sub: 'Full order lifecycle from Pending to Delivered with live tracking' },
    inventory: { title: 'Inventory & Pricing Studio', sub: 'Owner-set Base Price floors and dynamic price optimization' },
    refunds: { title: 'Refunds & 24h Policy Engine', sub: 'Strict rule evaluation: Auto-approved if cancelled <= 24h & not shipped' },
    reviews: { title: 'AI Customer Sentiment & Reviews', sub: 'Ollama LLM-powered review synthesis and catalog summary synchronization' },
    chat: { title: 'Omnipotent Admin AI Command Center', sub: 'Direct executive natural language control over all 7 agents & databases' }
  };

  if (titles[tabName]) {
    document.getElementById('pageTitle').innerText = titles[tabName].title;
    document.getElementById('pageSubtitle').innerText = titles[tabName].sub;
  }

  // Fetch fresh data for the selected tab on switch
  if (tabName === 'inventory') {
    fetch('/api/inventory').then(r => r.json()).then(d => {
      cachedProducts = d.products || [];
      renderInventoryTable(true);
    });
  } else if (tabName === 'orders') {
    fetch('/api/orders').then(r => r.json()).then(d => {
      cachedOrders = d.orders || [];
      renderOrdersTable();
    });
  } else if (tabName === 'refunds') {
    fetch('/api/orders').then(r => r.json()).then(d => {
      cachedOrders = d.orders || [];
      renderRefundsTable();
    });
  } else if (tabName === 'reviews') {
    fetch('/api/admin/reviews').then(r => r.json()).then(d => {
      cachedReviews = d.reviews || [];
      renderReviewsTab();
    });
  }

  if (window.lucide) window.lucide.createIcons();
}

function setupEventListeners() {
  document.getElementById('refreshDataBtn').addEventListener('click', loadAllAdminData);
  
  // Order status filter
  document.getElementById('orderStatusFilter').addEventListener('change', renderOrdersTable);

  // Trigger all agents button
  const triggerAllBtn = document.getElementById('triggerAllAgentsBtn');
  if (triggerAllBtn) {
    triggerAllBtn.addEventListener('click', async () => {
      triggerAllBtn.disabled = true;
      triggerAllBtn.innerHTML = `<i data-lucide="loader-2" class="spin"></i> Scanning Fleet...`;
      if (window.lucide) window.lucide.createIcons();
      for (const agentKey of ['price_manager', 'inventory_manager', 'order_manager', 'finance_manager', 'dispatcher', 'review_manager', 'ceo']) {
        await triggerAgentDirect(agentKey, false);
      }
      await loadAllAdminData();
      triggerAllBtn.disabled = false;
      triggerAllBtn.innerHTML = `<i data-lucide="play-circle"></i> <span>Trigger Full Fleet Scan</span>`;
      if (window.lucide) window.lucide.createIcons();
    });
  }

  // Add Product Form
  document.getElementById('openAddProductModalBtn').addEventListener('click', () => openModal('addProductModal'));
  document.getElementById('addProductForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      PRODUCT_NAME: document.getElementById('newProdName').value.trim(),
      PRODUCT_TYPE: document.getElementById('newProdType').value,
      PRODUCT_SIZE: document.getElementById('newProdSize').value.trim(),
      BASE_PRICE: parseFloat(document.getElementById('newProdBasePrice')?.value || document.getElementById('newProdPrice').value),
      PRICE: parseFloat(document.getElementById('newProdPrice').value),
      STOCK_REMAINING: parseInt(document.getElementById('newProdStock').value),
      DESCRIPTION: document.getElementById('newProdDesc').value.trim()
    };
    try {
      const res = await fetch('/api/admin/inventory/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        closeModal('addProductModal');
        document.getElementById('addProductForm').reset();
        await loadAllAdminData();
        alert(`✅ ${data.message}`);
      }
    } catch (err) { alert('Error adding product: ' + err); }
  });

  // Bulk Price Form
  document.getElementById('openBulkPriceModalBtn').addEventListener('click', () => openModal('bulkPriceModal'));
  document.getElementById('bulkPriceForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      category: document.getElementById('bulkCategory').value,
      percentage: parseFloat(document.getElementById('bulkPercentage').value)
    };
    try {
      const res = await fetch('/api/admin/inventory/bulk-price', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        closeModal('bulkPriceModal');
        await loadAllAdminData();
        alert(`✅ ${data.message}`);
      }
    } catch (err) { alert('Error applying price adjustment: ' + err); }
  });

  // Add Review Form
  document.getElementById('openAddReviewModalBtn').addEventListener('click', () => {
    populateReviewProductSelect();
    openModal('addReviewModal');
  });
  document.getElementById('addReviewForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
      product_id: document.getElementById('reviewProdSelect').value,
      customer_name: document.getElementById('reviewCustomerName').value.trim(),
      rating: parseInt(document.getElementById('reviewRating').value),
      review_text: document.getElementById('reviewText').value.trim()
    };
    try {
      const res = await fetch('/api/admin/reviews/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        closeModal('addReviewModal');
        document.getElementById('addReviewForm').reset();
        await loadAllAdminData();
        alert(`✅ Review recorded! Product rating recalculated.`);
      }
    } catch (err) { alert('Error adding review: ' + err); }
  });

  // Admin Chatbot Form
  const chatForm = document.getElementById('adminChatForm');
  const chatInput = document.getElementById('adminChatInput');
  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = chatInput.value.trim();
    if (!prompt) return;
    submitAdminChat(prompt);
  });

  // Prompt chips
  document.querySelectorAll('.admin-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const cmd = chip.dataset.cmd;
      if (cmd) submitAdminChat(cmd);
    });
  });
}

// Modal Helpers
window.openModal = function(id) {
  document.getElementById(id).classList.add('open');
};
window.closeModal = function(id) {
  document.getElementById(id).classList.remove('open');
};

// Data Fetching Helpers
const fetchJson = async (url, fallback) => {
  try {
    const res = await fetch(url);
    if (!res.ok) return fallback;
    return await res.json();
  } catch (e) {
    return fallback;
  }
};

// Full data load on startup / explicit Refresh button click
async function loadAllAdminData() {
  try {
    const [overview, agents, ordersData, invData, reviewsData, logsData, msgsData] = await Promise.all([
      fetchJson('/api/admin/overview', { kpis: {} }),
      fetchJson('/api/admin/agents/status', { agents: {} }),
      fetchJson('/api/orders', { orders: [] }),
      fetchJson('/api/inventory', { products: [] }),
      fetchJson('/api/admin/reviews', { reviews: [] }),
      fetchJson('/api/admin/agent-logs?limit=60', { logs: [] }),
      fetchJson('/api/admin/agent-messages?limit=60', { messages: [] })
    ]);

    cachedOrders = ordersData.orders || [];
    cachedProducts = invData.products || [];
    cachedReviews = reviewsData.reviews || [];
    cachedAgents = agents.agents || {};

    renderKPIs(overview.kpis || {});
    renderOverviewAgents(cachedAgents);
    renderOverviewMessageBus(msgsData.messages || []);
    renderAuditLogs(logsData.logs || []);
    renderFullAgentsGrid(cachedAgents);
    renderFullMessageBusTable(msgsData.messages || []);
    renderFullAgentLogsTable(logsData.logs || []);
    renderOrdersTable();
    renderInventoryTable(true);
    renderRefundsTable();
    renderReviewsTab();

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.error('Failed to sync admin telemetry:', err);
  }
}

// Calm telemetry polling (only updates KPI metrics, agent statuses, and message bus ticker — NEVER touches form tables)
async function pollTelemetryData() {
  // Only poll if on overview, agents, or chat tab to save bandwidth
  if (!['overview', 'agents', 'chat'].includes(currentTab)) return;

  try {
    const [overview, agents, msgsData] = await Promise.all([
      fetchJson('/api/admin/overview', { kpis: {} }),
      fetchJson('/api/admin/agents/status', { agents: {} }),
      fetchJson('/api/admin/agent-messages?limit=30', { messages: [] })
    ]);

    cachedAgents = agents.agents || {};

    renderKPIs(overview.kpis || {});
    renderOverviewAgents(cachedAgents);
    renderOverviewMessageBus(msgsData.messages || []);
    renderFullAgentsGrid(cachedAgents);
    renderFullMessageBusTable(msgsData.messages || []);

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.warn('Telemetry polling notice:', err);
  }
}

function renderKPIs(kpis) {
  const rev = kpis.total_revenue || 0;
  document.getElementById('kpiRevenue').innerText = `₹${rev.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  document.getElementById('kpiAgentActions').innerText = kpis.agent_autonomous_actions || 0;
  document.getElementById('kpiTotalOrders').innerText = kpis.total_orders || 0;
  document.getElementById('kpiActiveOrdersSub').innerText = `${kpis.active_orders || 0} active in pipeline (0% Tax)`;
  document.getElementById('kpiLowStock').innerText = kpis.low_stock_count || 0;
  document.getElementById('ordersCountBadge').innerText = kpis.total_orders || 0;
}

const AGENT_ICON_MAP = {
  price_manager: 'tag',
  inventory_manager: 'package',
  order_manager: 'clipboard-list',
  finance_manager: 'dollar-sign',
  refund_manager: 'rotate-ccw',
  dispatcher: 'truck',
  review_manager: 'star',
  ceo: 'briefcase'
};

function renderOverviewAgents(agents) {
  const container = document.getElementById('overviewAgentList');
  if (!container) return;

  container.innerHTML = Object.entries(agents).map(([key, a]) => `
    <div class="quick-agent-item">
      <div class="agent-info-left">
        <div class="agent-badge-icon">
          <i data-lucide="${AGENT_ICON_MAP[key] || 'bot'}"></i>
        </div>
        <div class="agent-name-wrap">
          <strong>${a.name}</strong>
          <span>${a.actions_count} cycles completed</span>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <span class="agent-status-pill active">${a.status}</span>
        <button class="action-btn-sm" onclick="triggerAgentDirect('${key}')" title="Trigger Instant Autonomous Scan">
          <i data-lucide="play" style="width: 12px; height: 12px;"></i>
        </button>
      </div>
    </div>
  `).join('');
}

function renderOverviewMessageBus(messages) {
  const container = document.getElementById('overviewMessageBusLogs');
  if (!container) return;
  if (messages.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">Awaiting inter-agent message traffic...</div>`;
    return;
  }
  container.innerHTML = messages.map(m => {
    const timeStr = m.timestamp ? new Date(m.timestamp).toLocaleTimeString() : '';
    let payloadText = '';
    try {
      payloadText = typeof m.payload === 'string' ? m.payload : JSON.stringify(m.payload);
    } catch (e) {
      payloadText = String(m.payload);
    }
    return `
      <div class="log-entry" style="border-left-color: #a855f7; background: rgba(168, 85, 247, 0.04);">
        <span class="log-time">[${timeStr}]</span>
        <strong style="color: #60a5fa;">${m.from}</strong>
        <span style="color: #a855f7; font-weight: 700;">➔</span>
        <strong style="color: #34d399;">${m.to}</strong>
        <span class="status-tag pending" style="margin-left: 0.35rem; font-size: 0.68rem; padding: 0.1rem 0.4rem;">${m.subject}</span>
        <div class="log-details" style="color: #e2e8f0; margin-top: 0.2rem; word-break: break-word;">${payloadText}</div>
      </div>
    `;
  }).join('');
}

function renderAuditLogs(logs) {
  const container = document.getElementById('overviewAuditLogs');
  if (!container) return;
  if (logs.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">No decision logs recorded yet.</div>`;
    return;
  }
  container.innerHTML = logs.map(l => {
    const timeStr = l.timestamp ? new Date(l.timestamp).toLocaleTimeString() : '';
    return `
      <div class="log-entry">
        <span class="log-time">[${timeStr}]</span>
        <span class="log-agent">${l.agent_name}:</span>
        <span class="log-action">${l.action}</span>
        <div class="log-details">${l.details}</div>
      </div>
    `;
  }).join('');
}

function renderFullAgentsGrid(agents) {
  const container = document.getElementById('fullAgentsGrid');
  if (!container) return;

  container.innerHTML = Object.entries(agents).map(([key, a]) => {
    const lastRunStr = a.last_run ? new Date(a.last_run).toLocaleTimeString() : 'Awaiting cycle';
    return `
      <div class="agent-full-card">
        <div class="card-top">
          <div class="card-icon-title">
            <div class="card-agent-icon">
              <i data-lucide="${AGENT_ICON_MAP[key] || 'bot'}"></i>
            </div>
            <div>
              <h4 style="font-size: 1rem; font-weight: 700;">${a.name}</h4>
              <span style="font-size: 0.72rem; color: #34d399;">● 24/7 Autonomous</span>
            </div>
          </div>
          <span class="status-tag delivered">${a.status}</span>
        </div>

        <p class="card-agent-desc">${a.description}</p>

        <div class="card-telemetry">
          <div class="card-telemetry-item">
            <span>Last Scan</span>
            <strong>${lastRunStr}</strong>
          </div>
          <div class="card-telemetry-item">
            <span>Autonomous Actions</span>
            <strong>${a.actions_count} cycles</strong>
          </div>
          <div class="card-telemetry-item">
            <span>Owner Power</span>
            <strong style="color: #60a5fa;">Autonomous</strong>
          </div>
        </div>

        <div class="card-actions">
          <button class="action-btn primary" style="width: 100%; justify-content: center; font-size: 0.8rem; padding: 0.5rem;" onclick="triggerAgentDirect('${key}')">
            <i data-lucide="zap" style="width: 14px; height: 14px;"></i> Trigger Autonomous Scan
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderFullMessageBusTable(messages) {
  const tbody = document.getElementById('fullMessageBusBody');
  if (!tbody) return;
  if (messages.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 2rem;">No inter-agent messages recorded yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = messages.map(m => {
    const dt = m.timestamp ? new Date(m.timestamp).toLocaleString() : '';
    let payloadStr = '';
    try {
      payloadStr = typeof m.payload === 'string' ? m.payload : JSON.stringify(m.payload, null, 2);
    } catch (e) {
      payloadStr = String(m.payload);
    }
    return `
      <tr>
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--text-dim);">${dt}</td>
        <td><strong style="color: #60a5fa;">${m.from}</strong></td>
        <td><strong style="color: #34d399;">${m.to}</strong></td>
        <td><span class="status-tag pending">${m.subject}</span></td>
        <td style="font-size: 0.78rem; font-family: 'JetBrains Mono', monospace; color: #e2e8f0; max-width: 500px; white-space: pre-wrap;">${payloadStr}</td>
      </tr>
    `;
  }).join('');
}

function renderFullAgentLogsTable(logs) {
  const tbody = document.getElementById('fullAgentLogsBody');
  if (!tbody) return;
  if (logs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 2rem;">No audit logs recorded yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = logs.map(l => {
    const dt = l.timestamp ? new Date(l.timestamp).toLocaleString() : '';
    return `
      <tr>
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--text-dim);">${dt}</td>
        <td><strong style="color: #c084fc;">${l.agent_name}</strong></td>
        <td><span class="status-tag dispatched">${l.action}</span></td>
        <td style="font-size: 0.82rem; color: #cbd5e1; max-width: 450px;">${l.details}</td>
        <td><span class="status-tag delivered">${l.autonomous ? '24/7 Auto' : 'Manual'}</span></td>
      </tr>
    `;
  }).join('');
}

// Direct Trigger Helper
window.triggerAgentDirect = async function(agentKey, reload = true) {
  try {
    const res = await fetch('/api/admin/agents/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_key: agentKey })
    });
    const data = await res.json();
    if (reload) {
      await loadAllAdminData();
      alert(`⚡ [${data.agent || agentKey}] Scan completed!\n${data.result?.details || 'Autonomous changes committed.'}`);
    }
  } catch (e) {
    console.error('Trigger error:', e);
  }
};

// Orders Table Render
function renderOrdersTable() {
  const tbody = document.getElementById('ordersTableBody');
  const filter = document.getElementById('orderStatusFilter').value;
  if (!tbody) return;

  const filtered = filter === 'ALL' ? cachedOrders : cachedOrders.filter(o => o.status === filter);

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2rem; color: var(--text-muted);">No orders matching filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(o => {
    const dateStr = new Date(o.created_at).toLocaleString();
    const stClass = (o.status || 'confirmed').toLowerCase();
    const trk = o.tracking_number || '—';
    const itemsSummary = o.items.map(i => `${i.quantity}x ${i.PRODUCT_NAME}`).join(', ');

    return `
      <tr>
        <td>
          <strong style="font-family: 'JetBrains Mono', monospace; color: #93c5fd;">${o.order_id}</strong>
          <div style="font-size: 0.7rem; color: var(--text-dim);">${dateStr}</div>
        </td>
        <td>
          <strong>${o.customer_name || 'Customer'}</strong>
          <div style="font-size: 0.72rem; color: var(--text-dim);">${o.shipping_address || ''}</div>
        </td>
        <td style="font-size: 0.78rem; max-width: 250px;">${itemsSummary}</td>
        <td><strong>₹${(o.total || 0).toFixed(2)}</strong></td>
        <td><code style="font-size: 0.75rem; color: #38bdf8;">${trk}</code></td>
        <td>
          <select class="admin-select" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;" onchange="updateOrderStatusInline('${o.order_id}', this.value)">
            <option value="Pending" ${o.status === 'Pending' ? 'selected' : ''}>Pending</option>
            <option value="Confirmed" ${o.status === 'Confirmed' ? 'selected' : ''}>Confirmed</option>
            <option value="Dispatched" ${o.status === 'Dispatched' ? 'selected' : ''}>Dispatched</option>
            <option value="Shipped" ${o.status === 'Shipped' ? 'selected' : ''}>Shipped</option>
            <option value="Delivered" ${o.status === 'Delivered' ? 'selected' : ''}>Delivered</option>
            <option value="Cancelled" ${o.status === 'Cancelled' ? 'selected' : ''}>Cancelled</option>
            <option value="Refunded" ${o.status === 'Refunded' ? 'selected' : ''}>Refunded</option>
          </select>
        </td>
        <td>
          ${o.status !== 'Refunded' && o.status !== 'Cancelled' ? `
            <button class="action-btn-sm" style="color: #fda4af; border-color: rgba(244,63,94,0.3);" onclick="cancelOrderWith24hRule('${o.order_id}')" title="Evaluate 24h & Non-Shipped Refund Rule">
              Cancel / Refund
            </button>
          ` : '<span style="font-size: 0.75rem; color: var(--text-dim);">Processed</span>'}
        </td>
      </tr>
    `;
  }).join('');
}

window.updateOrderStatusInline = async function(orderId, newStatus) {
  try {
    const res = await fetch(`/api/admin/orders/${orderId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    const data = await res.json();
    if (data.success) {
      await loadAllAdminData();
    } else {
      alert(`Status update failed: ${data.error}`);
    }
  } catch (err) { alert('Error updating status: ' + err); }
};

window.cancelOrderWith24hRule = async function(orderId) {
  if (!confirm(`Evaluate 24-hour cancellation rule for Order #${orderId}?\n\nRule: Auto-approved if cancelled <= 24 hours AND not yet shipped.`)) return;

  try {
    const res = await fetch(`/api/admin/orders/${orderId}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Store Owner Initiated' })
    });
    const data = await res.json();
    alert(data.message || (data.approved ? '✅ Refund Approved & Processed!' : `❌ Rejection: ${data.error}`));
    await loadAllAdminData();
  } catch (err) { alert('Cancellation evaluation error: ' + err); }
};

// Inventory Table Render
function renderInventoryTable(force = false) {
  const tbody = document.getElementById('inventoryTableBody');
  if (!tbody) return;

  // Protect active user input from being overwritten while typing
  if (!force && document.activeElement && tbody.contains(document.activeElement)) {
    return;
  }

  tbody.innerHTML = cachedProducts.map(p => {
    const isLow = p.STOCK_REMAINING <= 5;
    const basePrice = parseFloat(p.BASE_PRICE || p.PRICE || 0);
    const sellingPrice = parseFloat(p.PRICE || basePrice || 0);
    const diff = sellingPrice - basePrice;
    const pct = basePrice > 0 ? ((diff / basePrice) * 100) : 0;

    let deltaBadge = '';
    if (diff > 0.01) {
      deltaBadge = `<span class="price-badge-selling" title="Dynamic AI Markup">+₹${diff.toFixed(2)} (+${pct.toFixed(1)}% AI Surge)</span>`;
    } else {
      deltaBadge = `<span style="font-size: 0.65rem; color: #94a3b8;">🔒 At Base Floor</span>`;
    }

    return `
      <tr>
        <td>
          <strong style="color: #fff; font-size: 0.92rem;">${p.PRODUCT_NAME}</strong>
          <div style="font-size: 0.7rem; color: var(--text-dim); font-family: 'JetBrains Mono', monospace;">ID: ${p.id}</div>
        </td>
        <td><span class="status-tag pending">${p.PRODUCT_TYPE}</span></td>
        <td style="font-weight: 500;">${p.PRODUCT_SIZE}</td>
        <td>
          <input type="number" class="inline-input" id="stock_input_${p.id}" value="${p.STOCK_REMAINING}" min="0">
          ${isLow ? '<span style="color: #f59e0b; font-size: 0.7rem; display:block; margin-top:2px;">⚠️ Low stock</span>' : ''}
        </td>
        <td>
          <div class="price-box-base">
            <div style="display: flex; align-items: center; gap: 4px;">
              <span style="color: #a5b4fc; font-weight: 700; font-family: 'JetBrains Mono', monospace;">₹</span>
              <input type="number" step="0.01" class="inline-input price-input" id="base_price_input_${p.id}" value="${basePrice.toFixed(2)}" style="border-color: rgba(99,102,241,0.7); font-weight: 700; color: #a5b4fc; background: rgba(99,102,241,0.08);" title="Owner Base Price Floor (Agents cannot drop below this)">
            </div>
            <span class="price-badge-base">🔒 Owner Floor</span>
          </div>
        </td>
        <td>
          <div class="price-box-selling">
            <div style="display: flex; align-items: center; gap: 4px;">
              <span style="color: #34d399; font-weight: 700; font-family: 'JetBrains Mono', monospace;">₹</span>
              <input type="number" step="0.01" class="inline-input price-input" id="price_input_${p.id}" value="${sellingPrice.toFixed(2)}" style="font-weight: 700; color: #34d399; border-color: rgba(16,185,129,0.7); background: rgba(16,185,129,0.08);" title="Current Dynamic Selling Price set by AI Price Manager">
            </div>
            ${deltaBadge}
          </div>
        </td>
        <td style="font-weight: 600; color: #facc15;">⭐ ${p.RATING || 5.0}</td>
        <td>
          <div style="display: flex; gap: 4px;">
            <button class="action-btn-sm" style="background: rgba(16,185,129,0.25); border-color: rgba(16,185,129,0.5); color: #34d399; font-weight: 600;" onclick="saveInventoryInline('${p.id}')" title="Save Base Price & Selling Price">
              Save
            </button>
            <button class="action-btn-sm" onclick="quickRestockInline('${p.id}', 20)" title="Quick Restock +20 Units">
              +20 Stock
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// Floating Toast Notification Helper
function showAdminToast(message, type = 'success') {
  let container = document.getElementById('adminToastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'adminToastContainer';
    container.className = 'admin-toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `admin-toast ${type === 'error' ? 'error' : ''}`;
  toast.innerHTML = `
    <span style="font-size: 1.1rem;">${type === 'error' ? '❌' : '✅'}</span>
    <div>${message.replace(/\n/g, '<br/>')}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

window.saveInventoryInline = async function(productId) {
  const stockEl = document.getElementById(`stock_input_${productId}`);
  const basePriceEl = document.getElementById(`base_price_input_${productId}`);
  const priceEl = document.getElementById(`price_input_${productId}`);
  if (!stockEl || !basePriceEl || !priceEl) return;

  const stock = parseInt(stockEl.value);
  let basePrice = parseFloat(basePriceEl.value);
  let price = parseFloat(priceEl.value);

  if (isNaN(basePrice) || basePrice < 0) {
    showAdminToast("Please enter a valid positive Base Price.", "error");
    return;
  }
  if (isNaN(price) || price < basePrice) {
    showAdminToast(`⚠️ Selling Price cannot be below Base Price floor. Setting Selling Price to ₹${basePrice.toFixed(2)}.`);
    price = basePrice;
    priceEl.value = price.toFixed(2);
  }

  try {
    const res = await fetch('/api/admin/inventory/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, stock: stock, price: price, base_price: basePrice })
    });
    const data = await res.json();
    if (data.success) {
      const p = cachedProducts.find(x => x.id === productId);
      if (p) {
        p.STOCK_REMAINING = stock;
        p.BASE_PRICE = basePrice;
        p.PRICE = price;
      }
      renderInventoryTable(true);
      
      const savedRow = document.getElementById(`stock_input_${productId}`)?.closest('tr');
      if (savedRow) {
        savedRow.classList.add('row-saved-highlight');
        setTimeout(() => savedRow.classList.remove('row-saved-highlight'), 2000);
      }

      showAdminToast(`Updated SKU ${productId}: Base Floor ₹${basePrice.toLocaleString('en-IN')}, Selling Price ₹${price.toLocaleString('en-IN')}`);
    } else {
      showAdminToast(`Update failed: ${data.error || 'Unknown error'}`, 'error');
    }
  } catch (err) { showAdminToast('Error updating inventory: ' + err, 'error'); }
};

window.quickRestockInline = async function(productId, qty) {
  try {
    const p = cachedProducts.find(x => x.id === productId);
    const newStock = (p ? p.STOCK_REMAINING : 0) + qty;
    const res = await fetch('/api/admin/inventory/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, stock: newStock })
    });
    const data = await res.json();
    if (data.success) {
      if (p) p.STOCK_REMAINING = newStock;
      renderInventoryTable(true);
      showAdminToast(`Restocked SKU ${productId}: +${qty} units (New Stock: ${newStock})`);
    }
  } catch (err) { showAdminToast('Error restocking: ' + err, 'error'); }
};

// Refunds Table Render
function renderRefundsTable() {
  const tbody = document.getElementById('refundsTableBody');
  if (!tbody) return;

  tbody.innerHTML = cachedOrders.map(o => {
    const dt = new Date(o.created_at);
    const hoursElapsed = ((Date.now() - dt.getTime()) / (1000 * 3600)).toFixed(1);
    const isWithin24h = hoursElapsed <= 24.0;
    const isShipped = ['Shipped', 'Delivered'].includes(o.status);
    const isRefunded = o.status === 'Refunded';
    const isEligible = isWithin24h && !isShipped && !isRefunded;

    return `
      <tr>
        <td><strong>${o.order_id}</strong></td>
        <td style="font-size: 0.75rem; color: var(--text-dim);">${dt.toLocaleString()}</td>
        <td><strong>${hoursElapsed} hrs</strong></td>
        <td><span class="status-tag ${o.status.toLowerCase()}">${o.status}</span></td>
        <td>
          ${isRefunded ? '<span class="status-tag refunded">Refunded & Restocked</span>' :
            isEligible ? '<span class="status-tag delivered">✅ Eligible for 24h Auto-Refund</span>' :
            `<span class="status-tag cancelled">❌ Ineligible (${!isWithin24h ? '>24h' : 'Already Shipped'})</span>`
          }
        </td>
        <td><strong>₹${(o.total || 0).toFixed(2)}</strong></td>
        <td>
          ${!isRefunded ? `
            <button class="action-btn-sm" style="background: rgba(245,158,11,0.2); border-color: rgba(245,158,11,0.4);" onclick="cancelOrderWith24hRule('${o.order_id}')">
              ${isEligible ? '⚡ Auto-Refund (24h)' : 'Force Override Refund'}
            </button>
          ` : '<span style="font-size: 0.72rem; color: #34d399;">Processed</span>'}
        </td>
      </tr>
    `;
  }).join('');
}

// Reviews Tab Render
function renderReviewsTab() {
  const summariesContainer = document.getElementById('productSummariesList');
  const reviewsFeed = document.getElementById('customerReviewsFeed');
  if (!summariesContainer || !reviewsFeed) return;

  // Render Product AI Summaries
  summariesContainer.innerHTML = cachedProducts.map(p => {
    const summary = p.AI_REVIEW_SUMMARY || 'No AI summary generated yet. Click below to analyze reviews with Ollama LLM.';
    return `
      <div class="product-summary-card">
        <div class="summary-card-header">
          <div>
            <strong>${p.PRODUCT_NAME}</strong>
            <span style="font-size: 0.72rem; color: var(--text-dim); margin-left: 0.5rem;">(${p.PRODUCT_TYPE} • ⭐ ${p.RATING || 5.0})</span>
          </div>
          <button class="action-btn-sm" style="background: rgba(139,92,246,0.2); border-color: rgba(139,92,246,0.4);" onclick="triggerAISummaryGeneration('${p.id}')">
            ⚡ Generate AI Summary
          </button>
        </div>
        <div class="ai-summary-content">${summary}</div>
      </div>
    `;
  }).join('');

  // Render Customer Reviews Feed
  reviewsFeed.innerHTML = cachedReviews.map(r => `
    <div class="customer-review-card">
      <div class="review-card-top">
        <strong>${r.customer_name} on <span style="color: #93c5fd;">${r.product_name}</span></strong>
        <span style="color: #f59e0b;">${'⭐'.repeat(r.rating || 5)}</span>
      </div>
      <p class="review-card-text">"${r.review_text}"</p>
    </div>
  `).join('');
}

function populateReviewProductSelect() {
  const select = document.getElementById('reviewProdSelect');
  if (!select) return;
  select.innerHTML = cachedProducts.map(p => `
    <option value="${p.id}">${p.PRODUCT_NAME} (${p.PRODUCT_SIZE})</option>
  `).join('');
}

window.triggerAISummaryGeneration = async function(productId) {
  try {
    const res = await fetch('/api/admin/reviews/generate-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId })
    });
    const data = await res.json();
    if (data.success) {
      await loadAllAdminData();
      alert(`✨ AI Review Summary Generated for '${data.product_name}'!\n\nCatalog updated.`);
    }
  } catch (err) { alert('Error generating summary: ' + err); }
};

// Admin Chatbot Integration
let adminChatHistory = [];

async function submitAdminChat(prompt) {
  const input = document.getElementById('adminChatInput');
  const messagesBox = document.getElementById('adminChatMessages');
  input.value = '';

  // Append user bubble
  appendAdminMessage(prompt, 'user');
  adminChatHistory.push({ role: 'user', content: prompt });

  // Add temporary typing bubble
  const typingId = `typing_${Date.now()}`;
  const typingBubble = document.createElement('div');
  typingBubble.id = typingId;
  typingBubble.className = 'chat-bubble agent';
  typingBubble.innerHTML = `
    <div class="bubble-avatar">👑</div>
    <div class="bubble-content" style="color: var(--text-dim);"><i data-lucide="loader-2" class="spin"></i> Executing multi-agent commands...</div>
  `;
  messagesBox.appendChild(typingBubble);
  messagesBox.scrollTop = messagesBox.scrollHeight;
  if (window.lucide) window.lucide.createIcons();

  try {
    const res = await fetch('/api/admin/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        conversation_history: adminChatHistory
      })
    });
    const data = await res.json();

    // Remove typing bubble
    const tb = document.getElementById(typingId);
    if (tb) tb.remove();

    if (data.response) {
      appendAdminMessage(data.response, 'agent', data.tool_calls || []);
      adminChatHistory.push({ role: 'assistant', content: data.response });
    }

    // Refresh telemetry to reflect any database updates executed by tools
    await loadAllAdminData();
  } catch (err) {
    const tb = document.getElementById(typingId);
    if (tb) tb.remove();
    appendAdminMessage(`Execution error: ${err}`, 'agent');
  }
}

function appendAdminMessage(text, sender, toolCalls = []) {
  const box = document.getElementById('adminChatMessages');
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${sender}`;

  let toolTraceHtml = '';
  if (toolCalls && toolCalls.length > 0) {
    const agentIcons = {
      command_price_manager: '🏷️ Price Manager',
      command_inventory_manager: '📦 Inventory Manager',
      command_order_management: '📋 Order Management',
      command_finance_manager: '💰 Finance Manager',
      command_dispatcher: '🚚 Dispatcher Agent',
      command_review_manager: '⭐ Review & Feedback',
      get_ceo_report: '👔 CEO Strategic Briefing',
      ask_specialist_agent: '💬 Agent Consultation',
      send_agent_message: '⚡ Message Bus Broadcast',
      get_inter_agent_messages: '📨 Inter-Agent Bus',
      get_admin_dashboard_metrics: '📊 Store Telemetry',
      trigger_agent_cycle: '⚡ Autonomous Cycle'
    };

    toolTraceHtml = `
      <div style="margin-top: 0.75rem; padding-top: 0.6rem; border-top: 1px solid rgba(255,255,255,0.08); font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">
        <div style="color: #94a3b8; margin-bottom: 4px; font-weight: 600;">⚡ Multi-Agent Execution Trace:</div>
        ${toolCalls.map(tc => {
          const label = agentIcons[tc.name] || tc.name;
          return `<div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.2); border-radius: 6px; padding: 4px 8px; margin-top: 4px; color: #34d399;">
            <strong>${label}</strong>: <span style="color: #cbd5e1;">${JSON.stringify(tc.args || {})}</span>
          </div>`;
        }).join('')}
      </div>
    `;
  }

  bubble.innerHTML = `
    <div class="bubble-avatar">${sender === 'user' ? '👤' : '👑'}</div>
    <div class="bubble-content">
      <div>${formatMarkdown(text)}</div>
      ${toolTraceHtml}
    </div>
  `;
  box.appendChild(bubble);
  box.scrollTop = box.scrollHeight;
}

function formatMarkdown(text) {
  if (!text) return '';
  let formatted = text
    .replace(/### (.*?)\n/g, '<h4 style="margin: 8px 0 4px 0; color: #93c5fd;">$1</h4>')
    .replace(/## (.*?)\n/g, '<h3 style="margin: 10px 0 6px 0; color: #60a5fa;">$1</h3>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code style="background:rgba(0,0,0,0.3); padding:2px 4px; border-radius:4px; font-family:JetBrains Mono;">$1</code>')
    .replace(/^\s*[\-\*]\s+(.*)$/gm, '<li style="margin-left: 1rem;">$1</li>')
    .replace(/\n/g, '<br>');
  return formatted;
}

// Modal Handlers
window.openModal = function(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.add('open');
};

window.closeModal = function(modalId) {
  const m = document.getElementById(modalId);
  if (m) m.classList.remove('open');
};

document.getElementById('openAddProductModalBtn')?.addEventListener('click', () => openModal('addProductModal'));
document.getElementById('openBulkPriceModalBtn')?.addEventListener('click', () => openModal('bulkPriceModal'));

document.getElementById('addProductForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = document.getElementById('newProdName').value;
  const category = document.getElementById('newProdCategory').value;
  const size = document.getElementById('newProdSize').value;
  const basePrice = parseFloat(document.getElementById('newProdBasePrice').value);
  const price = parseFloat(document.getElementById('newProdPrice').value);
  const stock = parseInt(document.getElementById('newProdStock').value);
  const desc = document.getElementById('newProdDesc').value;

  if (price < basePrice) {
    alert(`⚠️ Initial Selling Price (₹${price}) cannot be below the Owner Base Price floor (₹${basePrice}).`);
    return;
  }

  try {
    const res = await fetch('/api/admin/inventory/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        PRODUCT_NAME: name,
        PRODUCT_TYPE: category,
        PRODUCT_SIZE: size,
        BASE_PRICE: basePrice,
        PRICE: price,
        STOCK_REMAINING: stock,
        DESCRIPTION: desc,
        IMAGE: `/static/images/${category === 'Mobiles' ? 'phone_flagship.svg' : category === 'Laptops' ? 'laptop_pro.svg' : category === 'Audio' ? 'earbuds_wireless.svg' : 'smartwatch.svg'}`
      })
    });
    const data = await res.json();
    if (data.success) {
      closeModal('addProductModal');
      await loadAllAdminData();
      alert(`✅ Product "${name}" added to catalog with Owner Floor ₹${basePrice.toFixed(2)}.`);
    }
  } catch (err) {
    alert('Error adding product: ' + err);
  }
});

document.getElementById('bulkPriceForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const category = document.getElementById('bulkCategory').value;
  const pct = parseFloat(document.getElementById('bulkPercentage').value);

  try {
    const res = await fetch('/api/admin/inventory/bulk-price', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, percentage_change: pct })
    });
    const data = await res.json();
    if (data.success) {
      closeModal('bulkPriceModal');
      await loadAllAdminData();
      alert(`✅ Bulk adjusted ${data.updated_count || 0} products by ${pct > 0 ? '+' : ''}${pct}%. All prices strictly clamped to Owner Base Price floors.`);
    }
  } catch (err) {
    alert('Error applying bulk price change: ' + err);
  }
});
