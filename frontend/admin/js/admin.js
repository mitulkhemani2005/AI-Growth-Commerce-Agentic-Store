// Admin Dashboard State & Logic
let currentTab = 'overview';
let cachedProducts = [];
let cachedOrders = [];
let cachedReviews = [];
let cachedAgents = {};
let cachedTreasury = {};
let cachedSalaries = {};
let cachedBuyers = [];
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
    overview: { title: 'Store Overview', sub: 'Real-time telemetry, automated agent actions, treasury P&L, and 5 AI buyers (INR ₹, 0% Tax)' },
    treasury: { title: 'CEO Treasury & Agent Salaries', sub: 'Manage initial ₹500K bank balance, wholesale inventory acquisition at base price, and agent salaries' },
    buyers: { title: '5 AI Autonomous Shoppers Fleet', sub: '5 Autonomous AI consumers with unlimited budgets browsing, purchasing, reviewing, and testing returns' },
    agents: { title: '24/7 Autonomous Agent Fleet', sub: '7 Autonomous agents collaborating in real time via Inter-Agent Message Bus' },
    orders: { title: 'Orders & Dispatch Pipeline', sub: 'Full order lifecycle from Pending to Delivered with live tracking' },
    inventory: { title: 'Inventory & Pricing Studio', sub: 'Owner-set Base Price floors and dynamic price optimization' },
    refunds: { title: 'Refunds & 24h Policy Engine', sub: 'Strict rule evaluation: Auto-approved if cancelled <= 24h & not shipped' },
    reviews: { title: 'AI Customer Sentiment & Reviews', sub: 'Ollama LLM-powered review synthesis and catalog summary synchronization' },
    chat: { title: 'CEO Command Center Chat', sub: 'Direct executive natural language control over all 7 agents, treasury & catalog' }
  };

  if (titles[tabName]) {
    document.getElementById('pageTitle').innerText = titles[tabName].title;
    document.getElementById('pageSubtitle').innerText = titles[tabName].sub;
  }

  // Fetch fresh data for the selected tab on switch
  if (tabName === 'treasury') {
    loadTreasuryData();
    loadSalariesData();
  } else if (tabName === 'buyers') {
    loadBuyersData();
  } else if (tabName === 'inventory') {
    fetch('/api/inventory').then(r => r.json()).then(d => {
      cachedProducts = d.products || [];
      renderInventoryTable(true);
    });
  } else if (tabName === 'orders') {
    fetch('/api/admin/orders').then(r => r.json()).then(d => {
      cachedOrders = d.orders || [];
      renderOrdersTable();
    });
  } else if (tabName === 'refunds') {
    fetch('/api/admin/orders').then(r => r.json()).then(d => {
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
    const [overview, agents, ordersData, invData, reviewsData, logsData, msgsData, treasuryData, salariesData, buyersData] = await Promise.all([
      fetchJson('/api/admin/overview', { kpis: {} }),
      fetchJson('/api/admin/agents/status', { agents: {} }),
      fetchJson('/api/admin/orders', { orders: [] }),
      fetchJson('/api/inventory', { products: [] }),

      fetchJson('/api/admin/reviews', { reviews: [] }),
      fetchJson('/api/admin/agent-logs?limit=60', { logs: [] }),
      fetchJson('/api/admin/agent-messages?limit=60', { messages: [] }),
      fetchJson('/api/admin/treasury?limit=30', { bank_balance: 1000.0, total_sales_revenue: 0.0, net_profit: 0.0, transactions: [] }),
      fetchJson('/api/admin/salaries', { salaries: [] }),
      fetchJson('/api/admin/buyers', { buyers: [] })
    ]);

    cachedOrders = ordersData.orders || [];
    cachedProducts = invData.products || [];
    cachedReviews = reviewsData.reviews || [];
    cachedAgents = agents.agents || {};
    cachedTreasury = treasuryData || {};
    cachedSalaries = salariesData || {};
    cachedBuyers = buyersData.buyers || [];

    renderKPIs(overview.kpis || {}, cachedTreasury);
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
    renderTreasuryTab(cachedTreasury);
    renderSalariesTab(cachedSalaries);
    renderBuyersTab(cachedBuyers);

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.error('Failed to sync admin telemetry:', err);
  }
}

// Calm telemetry polling (updates KPI metrics, agent statuses, treasury, and message bus ticker in real-time)
async function pollTelemetryData() {
  // Only poll if on overview, agents, treasury, buyers, or chat tab
  if (!['overview', 'agents', 'treasury', 'buyers', 'chat'].includes(currentTab)) return;

  try {
    const [overview, agents, msgsData, treasuryData, buyersData] = await Promise.all([
      fetchJson('/api/admin/overview', { kpis: {} }),
      fetchJson('/api/admin/agents/status', { agents: {} }),
      fetchJson('/api/admin/agent-messages?limit=30', { messages: [] }),
      fetchJson('/api/admin/treasury?limit=20', { bank_balance: 1000.0, total_sales_revenue: 0.0, net_profit: 0.0, transactions: [] }),
      fetchJson('/api/admin/buyers', { buyers: [] })
    ]);

    cachedAgents = agents.agents || {};
    cachedTreasury = treasuryData || {};
    cachedBuyers = buyersData.buyers || [];

    renderKPIs(overview.kpis || {}, cachedTreasury);
    renderOverviewAgents(cachedAgents);
    renderOverviewMessageBus(msgsData.messages || []);
    renderFullAgentsGrid(cachedAgents);
    renderFullMessageBusTable(msgsData.messages || []);

    if (currentTab === 'treasury') {
      renderTreasuryTab(cachedTreasury);
    } else if (currentTab === 'buyers') {
      renderBuyersTab(cachedBuyers);
    }

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.warn('Telemetry polling notice:', err);
  }
}

function renderKPIs(kpis, treasury = {}) {
  const bankBal = treasury.bank_balance !== undefined ? treasury.bank_balance : 1000.0;
  const rev = treasury.total_sales_revenue !== undefined ? treasury.total_sales_revenue : (kpis.total_revenue || 0);
  const profit = treasury.net_profit !== undefined ? treasury.net_profit : 0;
  const stockSpend = treasury.total_wholesale_stock_spend !== undefined ? treasury.total_wholesale_stock_spend : 0;
  const marginPct = treasury.gross_profit_margin_pct !== undefined ? treasury.gross_profit_margin_pct : 0;

  const bankEl = document.getElementById('kpiBankBalance');
  if (bankEl) bankEl.innerText = `₹${bankBal.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const revEl = document.getElementById('kpiRevenue');
  if (revEl) revEl.innerText = `₹${rev.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const profitEl = document.getElementById('kpiNetProfit');
  if (profitEl) {
    profitEl.innerText = `₹${profit.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    profitEl.style.color = profit >= 0 ? '#22c55e' : '#f43f5e';
  }

  const marginEl = document.getElementById('kpiProfitMargin');
  if (marginEl) marginEl.innerText = `Margin: ${marginPct}%`;

  const spendEl = document.getElementById('kpiInventorySpend');
  if (spendEl) spendEl.innerText = `₹${stockSpend.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const zeroStockCount = cachedProducts ? cachedProducts.filter(p => (p.STOCK_REMAINING || 0) <= 5).length : (kpis.low_stock_count || 0);
  const lowStockEl = document.getElementById('kpiLowStock');
  if (lowStockEl) lowStockEl.innerText = zeroStockCount;

  document.getElementById('kpiTotalOrders').innerText = kpis.total_orders || 0;
  document.getElementById('kpiActiveOrdersSub').innerText = `${kpis.active_orders || 0} active pipeline (0% Tax)`;
  document.getElementById('ordersCountBadge').innerText = kpis.total_orders || 0;

  const treasuryBadge = document.getElementById('treasuryBadge');
  if (treasuryBadge) {
    treasuryBadge.innerText = bankBal >= 100000 ? `₹${(bankBal / 1000).toFixed(0)}K` : `₹${bankBal.toFixed(0)}`;
  }
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
  
  // Message bus is strictly for internal Admin Specialist Agents (CEO, Price, Inventory, Order, Finance, Dispatcher, Review)
  const adminMsgs = (messages || []).filter(m => !(m.from || '').startsWith('AI Buyer') && !(m.to || '').startsWith('AI Buyer'));

  if (adminMsgs.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); text-align: center; padding: 2rem;">Awaiting inter-agent message traffic...</div>`;
    return;
  }
  container.innerHTML = adminMsgs.map(m => {
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
  
  // Exclusively admin specialist agents (CEO, Price, Inventory, Order, Finance, Dispatcher, Review)
  const adminMsgs = (messages || []).filter(m => !(m.from || '').startsWith('AI Buyer') && !(m.to || '').startsWith('AI Buyer'));

  if (adminMsgs.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 2rem;">No inter-agent messages recorded yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = adminMsgs.map(m => {
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
  const filterEl = document.getElementById('orderStatusFilter');
  const filter = filterEl ? filterEl.value : 'ALL';
  if (!tbody) return;

  const ordersList = cachedOrders || [];
  const filtered = filter === 'ALL' ? ordersList : ordersList.filter(o => (o.status || '').toLowerCase() === filter.toLowerCase());

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">No orders matching status filter '${filter}'.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(o => {
    const dateStr = o.created_at ? new Date(o.created_at).toLocaleString() : 'Just now';
    const trk = o.tracking_number || '—';
    const itemsList = o.items || [];
    const itemsSummary = itemsList.map(i => `${i.quantity || 1}x ${i.PRODUCT_NAME || i.product_name || i.id || 'Product'}`).join(', ') || '1x Catalog Item';
    const customer = o.customer_name || o.user_id || 'Customer';
    const isBuyer = (o.user_id || '').startsWith('buyer_');
    const totalVal = parseFloat(o.total) || 0.0;

    return `
      <tr>
        <td>
          <strong style="font-family: 'JetBrains Mono', monospace; color: #93c5fd;">${o.order_id}</strong>
          <div style="font-size: 0.7rem; color: var(--text-dim);">${dateStr}</div>
        </td>
        <td>
          <strong>${customer}</strong> ${isBuyer ? '<span class="status-tag pending" style="font-size: 0.65rem; padding: 1px 4px; margin-left: 4px;">AI Shopper</span>' : ''}
          <div style="font-size: 0.72rem; color: var(--text-dim);">${o.shipping_address || 'Online Delivery'}</div>
        </td>
        <td style="font-size: 0.78rem; max-width: 250px;">${itemsSummary}</td>
        <td><strong style="color: #34d399; font-family: monospace;">₹${totalVal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></td>
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
          <div style="display: flex; gap: 4px; flex-wrap: wrap;">
            <button class="action-btn-sm" style="background: rgba(16,185,129,0.25); border-color: rgba(16,185,129,0.5); color: #34d399; font-weight: 600;" onclick="saveInventoryInline('${p.id}')" title="Save Base Price & Selling Price">
              Save
            </button>
            <button class="action-btn-sm" style="background: rgba(6,182,212,0.2); border-color: rgba(6,182,212,0.5); color: #22d3ee; font-weight: 600;" onclick="openAcquireStockModal('${p.id}')" title="Acquire Wholesale Stock at BASE_PRICE">
              📦 Buy Wholesale
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

// =====================================================================
// 💰 TREASURY & WHOLESALE STOCK ACQUISITION FUNCTIONS
// =====================================================================

async function loadTreasuryData() {
  try {
    const data = await fetchJson('/api/admin/treasury?limit=30', {});
    cachedTreasury = data;
    renderTreasuryTab(data);
  } catch (err) {
    console.error('Error loading treasury:', err);
  }
}

function renderTreasuryTab(treasury) {
  const bankBal = treasury.bank_balance !== undefined ? treasury.bank_balance : 1000.0;
  const salesRev = treasury.total_sales_revenue || 0.0;
  const netProfit = treasury.net_profit || 0.0;
  const stockSpend = treasury.total_wholesale_stock_spend || 0.0;
  const salariesPaid = treasury.total_salary_expenses || 0.0;
  const refundsPaid = treasury.total_refunds_issued || 0.0;
  const roiPct = treasury.roi_pct || 0.0;
  const marginPct = treasury.gross_profit_margin_pct || 0.0;

  document.getElementById('treasuryBankBalance').innerText = `₹${bankBal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('treasurySalesRevenue').innerText = `₹${salesRev.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('treasurySalesCount').innerText = `${treasury.sales_transactions_count || 0} Sales`;

  const profitEl = document.getElementById('treasuryNetProfit');
  if (profitEl) {
    profitEl.innerText = `₹${netProfit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    profitEl.style.color = netProfit >= 0 ? '#22c55e' : '#f43f5e';
  }
  document.getElementById('treasuryMarginBadge').innerText = `${marginPct}% Margin`;
  document.getElementById('treasuryRoiText').innerText = `ROI: ${roiPct}%`;

  document.getElementById('treasuryStockSpend').innerText = `₹${stockSpend.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('treasuryUnitsAcquired').innerText = `${treasury.inventory_units_acquired || 0} Units Acquired`;

  document.getElementById('treasurySalariesPaid').innerText = `₹${salariesPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('treasuryRefunds').innerText = `₹${refundsPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('treasuryRefundCount').innerText = `${treasury.refund_transactions_count || 0} Refunds`;

  // Populate Quick Acquisition Select
  populateQuickAcquireSelect();

  // Render Treasury Ledger Feed
  renderTreasuryLedgerFeed(treasury.transactions || []);
}

function populateQuickAcquireSelect() {
  const select = document.getElementById('quickAcquireSelect');
  if (!select) return;
  const currVal = select.value;
  
  select.innerHTML = cachedProducts.map(p => {
    const isOut = (p.STOCK_REMAINING || 0) === 0;
    const baseP = parseFloat(p.BASE_PRICE || p.PRICE || 0);
    return `<option value="${p.id}" ${p.id === currVal ? 'selected' : ''}>${p.PRODUCT_NAME} (Stock: ${p.STOCK_REMAINING} | Base: ₹${baseP.toFixed(2)})${isOut ? ' ⚠️ OUT OF STOCK' : ''}</option>`;
  }).join('');

  onQuickAcquireProductChange();
}

window.onQuickAcquireProductChange = function() {
  const select = document.getElementById('quickAcquireSelect');
  if (!select) return;
  const prodId = select.value;
  const p = cachedProducts.find(x => x.id === prodId);
  if (!p) return;

  const baseP = parseFloat(p.BASE_PRICE || p.PRICE || 0);
  const sellP = parseFloat(p.PRICE || baseP);
  const unitMargin = sellP - baseP;
  const isOut = (p.STOCK_REMAINING || 0) === 0;

  const stockEl = document.getElementById('previewCurrentStock');
  if (stockEl) {
    stockEl.innerText = `${p.STOCK_REMAINING} Units ${isOut ? '(OUT OF STOCK - 0)' : ''}`;
    stockEl.className = isOut ? 'highlight-red' : 'highlight-green';
  }

  document.getElementById('previewBasePrice').innerText = `₹${baseP.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('previewSellingPrice').innerText = `₹${sellP.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  
  const marginEl = document.getElementById('previewUnitMargin');
  if (marginEl) {
    marginEl.innerText = `+₹${unitMargin.toLocaleString('en-IN', { minimumFractionDigits: 2 })} (+${((unitMargin / baseP) * 100).toFixed(1)}%)`;
  }

  recalculateQuickAcquireCost();
};

window.recalculateQuickAcquireCost = function() {
  const select = document.getElementById('quickAcquireSelect');
  const qtyInput = document.getElementById('quickAcquireQty');
  const costInput = document.getElementById('quickAcquireTotalCost');
  const remainingBalEl = document.getElementById('previewRemainingBalance');
  if (!select || !qtyInput || !costInput) return;

  const prodId = select.value;
  const p = cachedProducts.find(x => x.id === prodId);
  const qty = parseInt(qtyInput.value) || 0;
  const baseP = p ? parseFloat(p.BASE_PRICE || p.PRICE || 0) : 0;
  const totalCost = qty * baseP;

  costInput.value = `₹${totalCost.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  const currentBal = cachedTreasury.bank_balance !== undefined ? cachedTreasury.bank_balance : 1000.0;
  const remBal = currentBal - totalCost;

  if (remainingBalEl) {
    remainingBalEl.innerText = `₹${remBal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
    remainingBalEl.style.color = remBal >= 0 ? '#06b6d4' : '#f43f5e';
  }
};

window.submitQuickAcquire = async function() {
  const select = document.getElementById('quickAcquireSelect');
  const qtyInput = document.getElementById('quickAcquireQty');
  if (!select || !qtyInput) return;

  const prodId = select.value;
  const qty = parseInt(qtyInput.value) || 20;

  try {
    const res = await fetch('/api/admin/treasury/acquire-stock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: prodId, quantity: qty, actor: 'Store Owner' })
    });
    const data = await res.json();
    if (data.success) {
      showAdminToast(`✅ ${data.message}`);
      await loadAllAdminData();
    } else {
      showAdminToast(`❌ Acquisition failed: ${data.error || 'Check bank balance'}`, 'error');
    }
  } catch (err) {
    showAdminToast('Acquisition error: ' + err, 'error');
  }
};

window.openAcquireStockModal = function(productId = null) {
  const select = document.getElementById('modalAcquireProductSelect');
  if (!select) return;

  select.innerHTML = cachedProducts.map(p => {
    const isOut = (p.STOCK_REMAINING || 0) === 0;
    const baseP = parseFloat(p.BASE_PRICE || p.PRICE || 0);
    return `<option value="${p.id}" ${p.id === productId ? 'selected' : ''}>${p.PRODUCT_NAME} (Stock: ${p.STOCK_REMAINING} | Base Floor: ₹${baseP.toFixed(2)})${isOut ? ' ⚠️ 0-STOCK' : ''}</option>`;
  }).join('');

  if (productId) select.value = productId;
  onModalAcquireProductChange();
  openModal('acquireStockModal');
};

window.onModalAcquireProductChange = function() {
  const select = document.getElementById('modalAcquireProductSelect');
  if (!select) return;
  const prodId = select.value;
  const p = cachedProducts.find(x => x.id === prodId);
  if (!p) return;

  const baseP = parseFloat(p.BASE_PRICE || p.PRICE || 0);
  const sellP = parseFloat(p.PRICE || baseP);

  document.getElementById('modalPreviewBasePrice').innerText = `₹${baseP.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
  document.getElementById('modalPreviewCurrentStock').innerText = `${p.STOCK_REMAINING} Units`;
  document.getElementById('modalPreviewSellingPrice').innerText = `₹${sellP.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  const currentBal = cachedTreasury.bank_balance !== undefined ? cachedTreasury.bank_balance : 1000.0;
  document.getElementById('modalCurrentBankBalance').innerText = `₹${currentBal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;

  recalculateModalAcquireCost();
};

window.recalculateModalAcquireCost = function() {
  const select = document.getElementById('modalAcquireProductSelect');
  const qtyInput = document.getElementById('modalAcquireQty');
  const costInput = document.getElementById('modalAcquireTotalCost');
  if (!select || !qtyInput || !costInput) return;

  const prodId = select.value;
  const p = cachedProducts.find(x => x.id === prodId);
  const qty = parseInt(qtyInput.value) || 0;
  const baseP = p ? parseFloat(p.BASE_PRICE || p.PRICE || 0) : 0;
  costInput.value = `₹${(qty * baseP).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
};

window.submitModalAcquireStock = async function() {
  const select = document.getElementById('modalAcquireProductSelect');
  const qtyInput = document.getElementById('modalAcquireQty');
  if (!select || !qtyInput) return;

  const prodId = select.value;
  const qty = parseInt(qtyInput.value) || 20;

  try {
    const res = await fetch('/api/admin/treasury/acquire-stock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ product_id: prodId, quantity: qty, actor: 'Store Owner' })
    });
    const data = await res.json();
    if (data.success) {
      closeModal('acquireStockModal');
      showAdminToast(`✅ ${data.message}`);
      await loadAllAdminData();
    } else {
      showAdminToast(`❌ Acquisition failed: ${data.error || 'Insufficient treasury balance'}`, 'error');
    }
  } catch (err) {
    showAdminToast('Acquisition error: ' + err, 'error');
  }
};

function renderTreasuryLedgerFeed(transactions) {
  const container = document.getElementById('treasuryLedgerFeed');
  if (!container) return;

  if (transactions.length === 0) {
    container.innerHTML = `<div style="text-align: center; color: var(--text-dim); padding: 2rem;">No cash-flow transactions recorded yet.</div>`;
    return;
  }

  container.innerHTML = transactions.map(t => {
    const isPos = t.type === 'SALES_REVENUE';
    const typeLabel = t.type.replace('_', ' ');
    let typeClass = 'spend';
    if (t.type === 'SALES_REVENUE') typeClass = 'sale';
    else if (t.type === 'SALARY_PAYOUT') typeClass = 'salary';
    else if (t.type === 'REFUND_DEDUCTION') typeClass = 'refund';

    const timeStr = t.timestamp ? new Date(t.timestamp).toLocaleTimeString() : '';

    return `
      <div class="ledger-item">
        <div class="ledger-item-left">
          <span class="ledger-type-badge ${typeClass}">${typeLabel}</span>
          <div>
            <strong style="color: #f1f5f9;">${t.description}</strong>
            <div style="font-size: 0.7rem; color: var(--text-dim);">[${timeStr}] Balance after: ₹${(t.balance_after || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
          </div>
        </div>
        <div class="ledger-amount ${isPos ? 'pos' : 'neg'}">
          ${isPos ? '+' : '-'}₹${(t.amount || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
        </div>
      </div>
    `;
  }).join('');
}


// =====================================================================
// 💼 AGENT SALARY MANAGEMENT & INTERACTIVE NEGOTIATION FUNCTIONS
// =====================================================================

async function loadSalariesData() {
  try {
    const data = await fetchJson('/api/admin/salaries', { salaries: [] });
    cachedSalaries = data;
    renderSalariesTab(data);
  } catch (err) {
    console.error('Error loading salaries:', err);
  }
}

function renderSalariesTab(salariesData) {
  const tbody = document.getElementById('salariesTableBody');
  const label = document.getElementById('totalPayrollLabel');
  if (!tbody) return;

  const totalPayroll = salariesData.total_payroll_per_cycle || 300.0;
  if (label) {
    label.innerText = `Total Payroll: ₹${totalPayroll.toLocaleString('en-IN', { minimumFractionDigits: 2 })} / 100 cycles`;
  }

  const salariesList = salariesData.salaries || [];
  if (salariesList.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 2rem;">No agent salary records found.</td></tr>`;
    return;
  }

  tbody.innerHTML = salariesList.map(s => {
    const scoreColor = s.performance_score >= 90 ? '#10b981' : s.performance_score >= 80 ? '#60a5fa' : '#f59e0b';
    const statusClass = (s.negotiation_status || '').includes('Agreed') ? 'delivered' : 'pending';
    const lastPaidStr = s.last_paid_at ? new Date(s.last_paid_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' (' + new Date(s.last_paid_at).toLocaleDateString() + ')' : 'Awaiting Disbursal';
    const totalEarned = s.total_earned || 0.0;

    return `
      <tr>
        <td>
          <strong style="color: #fff; font-size: 0.92rem;">${s.agent_name}</strong>
        </td>
        <td><span class="status-tag pending" style="font-size: 0.72rem;">${s.role}</span></td>
        <td>
          <strong style="color: #38bdf8; font-size: 0.95rem; font-family: monospace;">₹${(s.salary_amount || 50).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
          <span style="font-size: 0.7rem; color: var(--text-dim); display: block;">/ 100 cycles (min ₹50)</span>
        </td>
        <td>
          <span class="salary-earned-pill">
            <i data-lucide="check-circle-2" style="width: 12px; height: 12px;"></i>
            ₹${totalEarned.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </span>
        </td>
        <td>
          <div style="display: flex; align-items: center; gap: 6px;">
            <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; min-width: 50px;">
              <div style="width: ${s.performance_score || 90}%; height: 100%; background: ${scoreColor};"></div>
            </div>
            <strong style="color: ${scoreColor}; font-size: 0.78rem;">${s.performance_score}/100</strong>
          </div>
        </td>
        <td><span class="status-tag ${statusClass}" style="font-size: 0.72rem;">${s.negotiation_status || 'Agreed'}</span></td>
        <td style="font-size: 0.75rem; color: var(--text-dim);">${lastPaidStr}</td>
        <td>
          <div style="display: flex; gap: 4px;">
            <button class="action-btn-sm" style="background: rgba(168,85,247,0.2); border-color: rgba(168,85,247,0.5); color: #c084fc; font-weight: 600;" onclick="openNegotiateModal('${s.agent_name}')" title="Negotiate Salary with Agent">
              <i data-lucide="message-circle" style="width: 12px; height: 12px;"></i> Negotiate
            </button>
            <button class="action-btn-sm" style="background: rgba(16,185,129,0.2); border-color: rgba(16,185,129,0.5); color: #34d399; font-weight: 600;" onclick="paySingleSalary('${s.agent_name}')" title="Pay Agent Salary from Treasury">
              <i data-lucide="send" style="width: 12px; height: 12px;"></i> Pay
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  if (window.lucide) window.lucide.createIcons();
}

window.openNegotiateModal = function(agentName) {
  const salariesList = cachedSalaries.salaries || [];
  const s = salariesList.find(x => x.agent_name === agentName);
  if (!s) return;

  document.getElementById('negAgentName').value = agentName;
  document.getElementById('negProposedSalary').value = s.salary_amount || 50;

  const header = document.getElementById('negModalAgentHeader');
  header.innerHTML = `
    <div>
      <h4 style="font-weight: 700; color: #fff;">${s.agent_name}</h4>
      <span style="font-size: 0.75rem; color: #94a3b8;">${s.role} | CEO Baseline Floor: ₹50.00 / 100 cycles</span>
    </div>
    <div style="text-align: right;">
      <strong style="color: #38bdf8; font-size: 1.1rem;">₹${(s.salary_amount || 50).toLocaleString('en-IN')} / 100c</strong>
      <div style="font-size: 0.72rem; color: #34d399;">Total Paid to Date: ₹${(s.total_earned || 0).toLocaleString('en-IN')}</div>
    </div>
  `;

  const thread = document.getElementById('negChatThread');
  thread.innerHTML = `
    <div class="neg-message agent">
      <strong>${s.agent_name}:</strong> Hello Store Owner & CEO! My current compensation is ₹${(s.salary_amount || 50).toLocaleString('en-IN')} per 100 cycles with a performance rating of ${s.performance_score}/100. Submit your proposed compensation (min ₹50 / 100 cycles) below to begin our salary discussion.
    </div>
  `;

  openModal('negotiateSalaryModal');
};

let lastNegotiationResponse = null;

window.submitSalaryProposal = async function() {
  const agentName = document.getElementById('negAgentName').value;
  const propSalary = parseFloat(document.getElementById('negProposedSalary').value);
  const rationale = document.getElementById('negRationale').value.trim();
  const thread = document.getElementById('negChatThread');
  const submitBtn = document.getElementById('negSubmitBtn');

  // Append user message
  const userDiv = document.createElement('div');
  userDiv.className = 'neg-message user';
  userDiv.innerHTML = `<strong>Store Owner:</strong> Proposing ₹${propSalary.toLocaleString('en-IN')} / 100 cycles | Rationale: "${rationale}"`;
  thread.appendChild(userDiv);

  // Append typing indicator
  const typingDiv = document.createElement('div');
  typingDiv.className = 'neg-message agent';
  typingDiv.id = 'negTyping';
  typingDiv.innerHTML = `<em>${agentName} is analyzing performance metrics and formulating counter-proposal...</em>`;
  thread.appendChild(typingDiv);
  thread.scrollTop = thread.scrollHeight;

  submitBtn.disabled = true;

  try {
    const res = await fetch('/api/admin/salaries/negotiate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        agent_name: agentName,
        proposed_salary: propSalary,
        rationale: rationale
      })
    });
    const data = await res.json();
    lastNegotiationResponse = data;

    const tEl = document.getElementById('negTyping');
    if (tEl) tEl.remove();

    const agentDiv = document.createElement('div');
    agentDiv.className = 'neg-message agent';
    agentDiv.innerHTML = `
      <strong>${agentName} (${data.status}):</strong> ${data.agent_response || data.message}
      <div style="margin-top: 6px; font-weight: 700; color: #34d399;">
        Agreed / Counter Salary: ₹${(data.final_salary || propSalary).toLocaleString('en-IN', { minimumFractionDigits: 2 })} / 100 cycles
      </div>
    `;
    thread.appendChild(agentDiv);
    thread.scrollTop = thread.scrollHeight;

    await loadSalariesData();
  } catch (err) {
    const tEl = document.getElementById('negTyping');
    if (tEl) tEl.remove();
    showAdminToast('Negotiation error: ' + err, 'error');
  } finally {
    submitBtn.disabled = false;
  }
};

window.acceptCounterProposal = async function() {
  if (!lastNegotiationResponse) {
    showAdminToast('No active negotiation proposal to accept.');
    return;
  }
  const agentName = document.getElementById('negAgentName').value;
  const finalSal = lastNegotiationResponse.final_salary;

  try {
    const res = await fetch('/api/admin/salaries/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: agentName, new_salary: finalSal, status: 'Agreed' })
    });
    const data = await res.json();
    if (data.success) {
      closeModal('negotiateSalaryModal');
      showAdminToast(`🤝 Agreement Sealed with ${agentName} at ₹${finalSal.toLocaleString('en-IN')} / 100 cycles!`);
      await loadSalariesData();
    }
  } catch (err) {
    showAdminToast('Error updating salary: ' + err, 'error');
  }
};

window.paySingleSalary = async function(agentName) {
  try {
    const res = await fetch('/api/admin/salaries/pay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: agentName, actor: 'Store Owner' })
    });
    const data = await res.json();
    if (data.success) {
      showAdminToast(`✅ Paid salary to ${agentName}! New Bank Balance: ₹${(data.new_bank_balance || 0).toLocaleString('en-IN')}`);
      await loadAllAdminData();
    } else {
      showAdminToast(`❌ Payment failed: ${data.error || 'Insufficient bank balance'}`, 'error');
    }
  } catch (err) {
    showAdminToast('Payment error: ' + err, 'error');
  }
};

window.disburseFullPayroll = async function() {
  if (!confirm('Disburse FULL team payroll to all 6 specialist agents from CEO Treasury Bank Balance?')) return;
  try {
    const res = await fetch('/api/admin/salaries/pay', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: 'all', actor: 'Store Owner' })
    });
    const data = await res.json();
    if (data.success) {
      showAdminToast(`✅ ${data.message}`);
      await loadAllAdminData();
    } else {
      showAdminToast(`❌ Payroll failed: ${data.error || 'Insufficient bank balance'}`, 'error');
    }
  } catch (err) {
    showAdminToast('Payroll error: ' + err, 'error');
  }
};


// =====================================================================
// 🛍️ 5 AI AUTONOMOUS SHOPPERS FLEET FUNCTIONS
// =====================================================================

async function loadBuyersData() {
  try {
    const data = await fetchJson('/api/admin/buyers', { buyers: [] });
    cachedBuyers = data.buyers || [];
    renderBuyersTab(cachedBuyers);
  } catch (err) {
    console.error('Error loading buyers:', err);
  }
}

function renderBuyersTab(buyersList) {
  const grid = document.getElementById('buyersCardsGrid');
  const tbody = document.getElementById('buyersActivityTableBody');
  if (!grid) return;

  const buyerAvatars = {
    buyer_alex: '💻',
    buyer_sophia: '🏷️',
    buyer_david: '🎧',
    buyer_elena: '💎',
    buyer_marcus: '⚡'
  };

  const nowSec = Date.now() / 1000;

  grid.innerHTML = buyersList.map(b => {
    const avatar = buyerAvatars[b.id] || '👤';
    const totalSpent = b.total_spent || 0.0;
    const ordersCount = b.orders_count || 0;
    const reviewsCount = b.reviews_written || b.reviews_count || 0;
    const returnsCount = b.returns_count || 0;
    const nextTs = parseFloat(b.next_purchase_ts || 0);

    let countdownText = 'Shopping anytime (0-5m)';
    if (nextTs > nowSec) {
      const diffSec = Math.max(0, Math.round(nextTs - nowSec));
      const mins = Math.floor(diffSec / 60);
      const secs = diffSec % 60;
      countdownText = mins > 0 ? `Next order in ~${mins}m ${secs}s` : `Next order in ~${secs}s`;
    } else if (nextTs > 0) {
      countdownText = 'Ready to shop (evaluating)';
    }

    return `
      <div class="buyer-card">
        <div>
          <div class="buyer-card-header">
            <div class="buyer-avatar">${avatar}</div>
            <div class="buyer-info">
              <h4>${b.name}</h4>
              <span class="buyer-persona-tag">${b.persona_title || b.persona || 'AI Shopper'}</span>
            </div>
          </div>
          <p class="buyer-desc">${b.description}</p>
          <div class="buyer-live-status" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span class="pulsing-dot" style="width: 8px; height: 8px;"></span>
              <span style="font-size: 0.78rem;">${b.status || 'Browsing catalog'}</span>
            </div>
            <span class="buyer-countdown-badge"><i data-lucide="clock" style="width: 11px; height: 11px;"></i> ${countdownText}</span>
          </div>
          <div class="buyer-metrics-row">
            <div class="buyer-metric">
              <span>Lifetime Spend</span>
              <strong style="color: #34d399;">₹${totalSpent.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong>
            </div>
            <div class="buyer-metric">
              <span>Orders Placed</span>
              <strong>${ordersCount}</strong>
            </div>
            <div class="buyer-metric">
              <span>Reviews / Returns</span>
              <strong>${reviewsCount} / ${returnsCount}</strong>
            </div>
          </div>
        </div>
        <div class="buyer-card-actions">
          <button class="action-btn primary" style="width: 100%; justify-content: center; font-size: 0.8rem;" onclick="triggerBuyer('${b.id}')">
            <i data-lucide="shopping-cart"></i> ⚡ Quick Buy Now (AP2)
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Render Activity Stream Table from Orders
  if (tbody) {
    const buyerOrders = cachedOrders.filter(o => o.user_id && o.user_id.startsWith('buyer_'));
    if (buyerOrders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 2rem;">No AI shopper orders placed yet. Trigger a shopping cycle above!</td></tr>`;
    } else {
      tbody.innerHTML = buyerOrders.map(o => {
        const timeStr = o.created_at ? new Date(o.created_at).toLocaleString() : '';
        const itemNames = (o.items || []).map(i => i.PRODUCT_NAME || i.product_id).join(', ');
        return `
          <tr>
            <td><strong style="color: #c084fc;">${o.customer_name || o.user_id}</strong></td>
            <td><span class="status-tag delivered">Purchase</span></td>
            <td style="color: #fff;">${itemNames || 'Catalog Items'}</td>
            <td style="font-weight: 700; color: #34d399; font-family: monospace;">₹${(o.total || 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</td>
            <td><span class="status-tag pending" style="font-size: 0.72rem;">AP2 1-Click Auto</span></td>
            <td style="font-size: 0.75rem; color: #facc15;">⭐⭐⭐⭐⭐ Verified</td>
            <td><span class="status-tag ${o.status === 'Delivered' ? 'delivered' : 'dispatched'}">${o.status}</span></td>
            <td style="font-size: 0.72rem; color: var(--text-dim);">${timeStr}</td>
          </tr>
        `;
      }).join('');
    }
  }

  if (window.lucide) window.lucide.createIcons();
}

window.triggerBuyer = async function(buyerId) {
  try {
    showAdminToast(`🛒 Triggering AI Buyer ${buyerId}...`);
    const res = await fetch('/api/admin/buyers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ buyer_id: buyerId })
    });
    const data = await res.json();
    if (data.success) {
      showAdminToast(`✅ ${data.shopper}: ${data.message}`);
      await loadAllAdminData();
    } else {
      showAdminToast(`⚠️ ${data.error || 'Buyer evaluated catalog'}`, 'error');
    }
  } catch (err) {
    showAdminToast('Buyer trigger error: ' + err, 'error');
  }
};

window.triggerAllBuyers = async function() {
  try {
    showAdminToast('🛍️ Triggering all 5 AI Shoppers...');
    const res = await fetch('/api/admin/buyers/trigger', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ buyer_id: 'all' })
    });
    const data = await res.json();
    if (data.success) {
      showAdminToast('✅ All 5 AI Shoppers completed catalog evaluation!');
      await loadAllAdminData();
    }
  } catch (err) {
    showAdminToast('Error triggering all buyers: ' + err, 'error');
  }
};

window.toggleBuyersSimulation = async function() {
  try {
    const res = await fetch('/api/admin/buyers/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    const data = await res.json();
    const btnText = document.getElementById('toggleBuyersText');
    if (btnText) {
      btnText.innerText = data.enabled ? 'Simulation: ACTIVE' : 'Simulation: PAUSED';
    }
    showAdminToast(data.message);
  } catch (err) {
    showAdminToast('Toggle error: ' + err, 'error');
  }
};


// =====================================================================
// 👔 CEO MULTI-AGENT ROUNDTABLE DISCUSSION ROOM
// =====================================================================

window.onMeetingPresetChange = function() {
  const select = document.getElementById('meetingPresetSelect');
  const input = document.getElementById('meetingTopicInput');
  if (!select || !input) return;

  const presets = {
    restock: 'Wholesale inventory restock budget, base price margin calibration, and supplier lead times',
    pricing: 'Dynamic pricing optimization, scarcity discounts, and protecting base price floors',
    salaries: 'Specialist agent performance ratings, compensation proposals, and treasury budget review',
    buyers: '5 AI Autonomous buyer traffic trends, AP2 checkout velocity, and 24h return policy SLA'
  };

  if (presets[select.value]) {
    input.value = presets[select.value];
  }
};

window.startCEOMeeting = async function() {
  const input = document.getElementById('meetingTopicInput');
  const box = document.getElementById('meetingTranscriptBox');
  const btn = document.getElementById('conveneMeetingBtn');
  if (!input || !box) return;

  const topic = input.value.trim();
  if (!topic) {
    showAdminToast('Please enter a meeting agenda.');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="spin"></i> Convening Fleet...`;
  if (window.lucide) window.lucide.createIcons();

  box.innerHTML = `
    <div style="text-align: center; padding: 2rem; color: #a855f7;">
      <i data-lucide="loader-2" class="spin" style="width: 36px; height: 36px; margin-bottom: 0.5rem;"></i>
      <p>CEO Agent is convening all 6 specialist agents (Price, Inventory, Order, Finance, Dispatcher, Review)...</p>
    </div>
  `;
  if (window.lucide) window.lucide.createIcons();

  try {
    const res = await fetch('/api/admin/ceo/discussion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic: topic, participants: 'ALL_AGENTS' })
    });
    const data = await res.json();

    if (data.success && data.transcript) {
      box.innerHTML = data.transcript.map(t => {
        let speakerClass = 'ceo';
        const spLower = t.speaker.toLowerCase();
        if (spLower.includes('price')) speakerClass = 'price';
        else if (spLower.includes('invent')) speakerClass = 'inventory';
        else if (spLower.includes('finan')) speakerClass = 'finance';
        else if (spLower.includes('order')) speakerClass = 'order';
        else if (spLower.includes('dispatch')) speakerClass = 'dispatcher';
        else if (spLower.includes('review')) speakerClass = 'review';

        return `
          <div class="transcript-bubble ${speakerClass}">
            <div class="bubble-speaker">
              ${t.speaker}
              <span class="bubble-role">${t.role}</span>
            </div>
            <div class="bubble-text">${formatMarkdown(t.statement)}</div>
          </div>
        `;
      }).join('');

      showAdminToast('👔 CEO Executive Roundtable Concluded & Consensus Reached!');
      await loadAllAdminData();
    } else {
      box.innerHTML = `<div style="color: #f43f5e; padding: 1rem;">Discussion error: ${data.error || 'Failed to convene meeting.'}</div>`;
    }
  } catch (err) {
    box.innerHTML = `<div style="color: #f43f5e; padding: 1rem;">Meeting error: ${err}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="play"></i> <span>Convene Meeting</span>`;
    if (window.lucide) window.lucide.createIcons();
  }
};


// =====================================================================
// 🔄 STORE RESET TO INITIAL 0-STOCK STATE
// =====================================================================

window.openResetStoreConfirm = function() {
  openModal('resetStoreConfirmModal');
};

window.confirmResetStoreComplete = async function() {
  try {
    closeModal('resetStoreConfirmModal');
    showAdminToast('🔄 Resetting store to initial 0-stock state...');
    const res = await fetch('/api/admin/reset-store', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.success) {
      showAdminToast(`✅ ${data.message}`);
      await loadAllAdminData();
    }
  } catch (err) {
    showAdminToast('Reset error: ' + err, 'error');
  }
};

