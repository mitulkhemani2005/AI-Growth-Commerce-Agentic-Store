// Admin Dashboard State & Logic
let currentTab = 'overview';
let cachedProducts = [];
let cachedOrders = [];
let cachedReviews = [];
let cachedAgents = {};
let pollingInterval = null;

document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) window.lucide.createIcons();
  setupNavigation();
  setupEventListeners();
  loadAllAdminData();
  
  // Auto-refresh telemetry every 8 seconds for live 24/7 view
  pollingInterval = setInterval(loadAllAdminData, 8000);
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
    overview: { title: 'Store Overview', sub: 'Real-time telemetry, automated agent actions, and store health' },
    agents: { title: '24/7 Autonomous Agent Fleet', sub: '6 Specialist agents monitoring, optimizing, and dispatching around the clock' },
    orders: { title: 'Orders & Dispatch Pipeline', sub: 'Full order lifecycle from Pending to Delivered with live tracking' },
    inventory: { title: 'Inventory & Pricing Studio', sub: 'Direct inline control over warehouse stock levels and catalog prices' },
    refunds: { title: 'Refunds & 24h Policy Engine', sub: 'Strict rule evaluation: Auto-approved if cancelled <= 24h & not shipped' },
    reviews: { title: 'AI Customer Sentiment & Reviews', sub: 'Groq LLM-powered review synthesis and catalog summary synchronization' },
    chat: { title: 'Omnipotent Admin AI Command Center', sub: 'Direct executive natural language control over all 6 agents & databases' }
  };

  if (titles[tabName]) {
    document.getElementById('pageTitle').innerText = titles[tabName].title;
    document.getElementById('pageSubtitle').innerText = titles[tabName].sub;
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
      for (const agentKey of ['price_manager', 'inventory_manager', 'order_manager', 'refund_manager', 'dispatcher', 'review_manager']) {
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

// Data Fetching
async function loadAllAdminData() {
  try {
    const [overviewRes, agentRes, ordersRes, invRes, reviewsRes, logsRes] = await Promise.all([
      fetch('/api/admin/overview'),
      fetch('/api/admin/agents/status'),
      fetch('/api/orders'),
      fetch('/api/inventory'),
      fetch('/api/admin/reviews'),
      fetch('/api/admin/agent-logs?limit=40')
    ]);

    const overview = await overviewRes.json();
    const agents = await agentRes.json();
    const ordersData = await ordersRes.json();
    const invData = await invRes.json();
    const reviewsData = await reviewsRes.json();
    const logsData = await logsRes.json();

    cachedOrders = ordersData.orders || [];
    cachedProducts = invData.products || [];
    cachedReviews = reviewsData.reviews || [];
    cachedAgents = agents.agents || {};

    renderKPIs(overview.kpis || {});
    renderOverviewAgents(cachedAgents);
    renderAuditLogs(logsData.logs || []);
    renderFullAgentsGrid(cachedAgents);
    renderFullAgentLogsTable(logsData.logs || []);
    renderOrdersTable();
    renderInventoryTable();
    renderRefundsTable();
    renderReviewsTab();

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.error('Failed to sync admin telemetry:', err);
  }
}

function renderKPIs(kpis) {
  document.getElementById('kpiRevenue').innerText = `$${(kpis.total_revenue || 0).toFixed(2)}`;
  document.getElementById('kpiAgentActions').innerText = kpis.agent_autonomous_actions || 0;
  document.getElementById('kpiTotalOrders').innerText = kpis.total_orders || 0;
  document.getElementById('kpiActiveOrdersSub').innerText = `${kpis.active_orders || 0} active in pipeline`;
  document.getElementById('kpiLowStock').innerText = kpis.low_stock_count || 0;
  document.getElementById('ordersCountBadge').innerText = kpis.total_orders || 0;
}

function renderOverviewAgents(agents) {
  const container = document.getElementById('overviewAgentList');
  if (!container) return;
  
  const iconMap = {
    price_manager: 'tag',
    inventory_manager: 'package',
    order_manager: 'clipboard-list',
    refund_manager: 'rotate-ccw',
    dispatcher: 'truck',
    review_manager: 'star'
  };

  container.innerHTML = Object.entries(agents).map(([key, a]) => `
    <div class="quick-agent-item">
      <div class="agent-info-left">
        <div class="agent-badge-icon">
          <i data-lucide="${iconMap[key] || 'bot'}"></i>
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

function renderAuditLogs(logs) {
  const container = document.getElementById('overviewAuditLogs');
  if (!container) return;
  if (logs.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">No logs recorded yet.</div>`;
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

  const iconMap = {
    price_manager: 'tag',
    inventory_manager: 'package',
    order_manager: 'clipboard-list',
    refund_manager: 'rotate-ccw',
    dispatcher: 'truck',
    review_manager: 'star'
  };

  container.innerHTML = Object.entries(agents).map(([key, a]) => {
    const lastRunStr = a.last_run ? new Date(a.last_run).toLocaleTimeString() : 'Awaiting cycle';
    return `
      <div class="agent-full-card">
        <div class="card-top">
          <div class="card-icon-title">
            <div class="card-agent-icon">
              <i data-lucide="${iconMap[key] || 'bot'}"></i>
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

function renderFullAgentLogsTable(logs) {
  const tbody = document.getElementById('fullAgentLogsBody');
  if (!tbody) return;
  tbody.innerHTML = logs.map(l => {
    const dt = l.timestamp ? new Date(l.timestamp).toLocaleString() : '';
    return `
      <tr>
        <td style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: var(--text-dim);">${dt}</td>
        <td><strong style="color: #c084fc;">${l.agent_name}</strong></td>
        <td><span class="status-tag dispatched">${l.action}</span></td>
        <td style="font-size: 0.82rem; color: #cbd5e1; max-width: 450px;">${l.details}</td>
        <td><span class="status-tag delivered">Yes (24/7)</span></td>
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
        <td><strong>$${(o.total || 0).toFixed(2)}</strong></td>
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
function renderInventoryTable() {
  const tbody = document.getElementById('inventoryTableBody');
  if (!tbody) return;

  tbody.innerHTML = cachedProducts.map(p => {
    const isLow = p.STOCK_REMAINING <= 5;
    return `
      <tr>
        <td>
          <strong>${p.PRODUCT_NAME}</strong>
          <div style="font-size: 0.7rem; color: var(--text-dim);">ID: ${p.id}</div>
        </td>
        <td><span class="status-tag pending">${p.PRODUCT_TYPE}</span></td>
        <td>${p.PRODUCT_SIZE}</td>
        <td>
          <input type="number" class="inline-input" id="stock_input_${p.id}" value="${p.STOCK_REMAINING}" min="0">
          ${isLow ? '<span style="color: #f59e0b; font-size: 0.7rem; display:block;">⚠️ Low stock</span>' : ''}
        </td>
        <td>
          <input type="number" step="0.01" class="inline-input" id="price_input_${p.id}" value="${p.PRICE}">
        </td>
        <td>⭐ ${p.RATING || 5.0}</td>
        <td>
          <button class="action-btn-sm" style="background: rgba(16,185,129,0.2); border-color: rgba(16,185,129,0.4);" onclick="saveInventoryInline('${p.id}')">
            Save
          </button>
          <button class="action-btn-sm" onclick="quickRestockInline('${p.id}', 20)" title="Quick Restock +20 Units">
            +20 Stock
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

window.saveInventoryInline = async function(productId) {
  const stock = parseInt(document.getElementById(`stock_input_${productId}`).value);
  const price = parseFloat(document.getElementById(`price_input_${productId}`).value);

  try {
    const res = await fetch('/api/admin/inventory/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: productId, stock: stock, price: price })
    });
    const data = await res.json();
    if (data.success) {
      await loadAllAdminData();
      alert(`✅ Updated SKU ${productId} (Stock: ${stock}, Price: $${price})`);
    }
  } catch (err) { alert('Error updating inventory: ' + err); }
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
    await loadAllAdminData();
  } catch (err) { alert('Error restocking: ' + err); }
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
        <td><strong>$${(o.total || 0).toFixed(2)}</strong></td>
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
    const summary = p.AI_REVIEW_SUMMARY || 'No AI summary generated yet. Click below to analyze reviews with Groq LLM.';
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
    toolTraceHtml = `
      <div style="margin-top: 0.6rem; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.06); font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #34d399;">
        ${toolCalls.map(tc => `<div>⚡ <strong>${tc.name}</strong>: ${JSON.stringify(tc.args)}</div>`).join('')}
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
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code style="background:rgba(0,0,0,0.3); padding:2px 4px; border-radius:4px; font-family:JetBrains Mono;">$1</code>')
    .replace(/\n/g, '<br>');
}
