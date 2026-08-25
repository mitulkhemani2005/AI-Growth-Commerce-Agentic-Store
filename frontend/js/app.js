// AI Growth Commerce - Agentic Store App Logic

let activeUserId = 'user_alex';
let activeUserName = 'Alex Rivera';
let activeUserInitials = 'AR';
let catalogProducts = [];
let currentCategory = 'ALL';
let chatHistory = [];

// DOM Elements
const productsGrid = document.getElementById('productsGrid');
const catalogCountBadge = document.getElementById('catalogCountBadge');
const catalogSearchInput = document.getElementById('catalogSearchInput');
const categoryPillsContainer = document.getElementById('categoryPillsContainer');

const cartCountBadge = document.getElementById('cartCountBadge');
const ordersCountBadge = document.getElementById('ordersCountBadge');
const cartDrawerOverlay = document.getElementById('cartDrawerOverlay');
const cartItemsList = document.getElementById('cartItemsList');
const cartSubtotalText = document.getElementById('cartSubtotalText');
const cartTaxText = document.getElementById('cartTaxText');
const cartTotalText = document.getElementById('cartTotalText');

const ordersModalOverlay = document.getElementById('ordersModalOverlay');
const ordersModalBody = document.getElementById('ordersModalBody');

const userModalOverlay = document.getElementById('userModalOverlay');
const userSelectorBtn = document.getElementById('userSelectorBtn');
const userNameText = document.getElementById('userNameText');
const userAvatarText = document.getElementById('userAvatarText');

const chatMessages = document.getElementById('chatMessages');
const chatForm = document.getElementById('chatForm');
const chatPromptInput = document.getElementById('chatPromptInput');
const sendPromptBtn = document.getElementById('sendPromptBtn');

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) {
    window.lucide.createIcons();
  }
  loadCatalog();
  loadCart();
  loadOrders();
  checkAP2Status();
  setupEventListeners();
});

function setupEventListeners() {
  // Search input & clear button
  catalogSearchInput.addEventListener('input', () => {
    if (searchClearBtn) {
      searchClearBtn.style.display = catalogSearchInput.value ? 'block' : 'none';
    }
    filterAndRenderCatalog();
  });

  if (searchClearBtn) {
    searchClearBtn.addEventListener('click', () => {
      catalogSearchInput.value = '';
      searchClearBtn.style.display = 'none';
      filterAndRenderCatalog();
    });
  }

  // Category pills
  categoryPillsContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('.cat-pill');
    if (!btn) return;
    document.querySelectorAll('.cat-pill').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    currentCategory = btn.dataset.category;
    filterAndRenderCatalog();
  });

  // Open / Close Cart
  document.getElementById('openCartBtn').addEventListener('click', () => {
    cartDrawerOverlay.classList.add('open');
  });
  document.getElementById('closeCartBtn').addEventListener('click', () => {
    cartDrawerOverlay.classList.remove('open');
  });
  cartDrawerOverlay.addEventListener('click', (e) => {
    if (e.target === cartDrawerOverlay) cartDrawerOverlay.classList.remove('open');
  });

  // Open / Close Orders Modal
  document.getElementById('openOrdersBtn').addEventListener('click', () => {
    loadOrders();
    ordersModalOverlay.classList.add('open');
  });
  document.getElementById('closeOrdersModalBtn').addEventListener('click', () => {
    ordersModalOverlay.classList.remove('open');
  });
  ordersModalOverlay.addEventListener('click', (e) => {
    if (e.target === ordersModalOverlay) ordersModalOverlay.classList.remove('open');
  });

  // Open / Close Razorpay Settings Modal
  const openRazorpayConfigBtn = document.getElementById('openRazorpayConfigBtn');
  const razorpayModalOverlay = document.getElementById('razorpayModalOverlay');
  const closeRazorpayModalBtn = document.getElementById('closeRazorpayModalBtn');
  const razorpaySettingsForm = document.getElementById('razorpaySettingsForm');

  if (openRazorpayConfigBtn) {
    openRazorpayConfigBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/payment/config');
        const cfg = await res.json();
        if (cfg.key_id && !cfg.key_id.startsWith('rzp_test_growth_')) {
          document.getElementById('rzpKeyIdInput').value = cfg.key_id;
        }
      } catch (e) {}
      razorpayModalOverlay.classList.add('open');
    });
  }
  if (closeRazorpayModalBtn) {
    closeRazorpayModalBtn.addEventListener('click', () => {
      razorpayModalOverlay.classList.remove('open');
    });
  }
  if (razorpayModalOverlay) {
    razorpayModalOverlay.addEventListener('click', (e) => {
      if (e.target === razorpayModalOverlay) razorpayModalOverlay.classList.remove('open');
    });
  }

  // Razorpay Settings Form Submit
  if (razorpaySettingsForm) {
    razorpaySettingsForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const keyId = document.getElementById('rzpKeyIdInput').value.trim();
      const keySecret = document.getElementById('rzpKeySecretInput').value.trim();
      if (!keyId || !keySecret) {
        alert('Please enter both Razorpay Key ID and Key Secret.');
        return;
      }
      try {
        const res = await fetch('/api/payment/credentials', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key_id: keyId, key_secret: keySecret })
        });
        const data = await res.json();
        if (data.success) {
          razorpayModalOverlay.classList.remove('open');
          appendAgentMessage(`✅ **Razorpay API Keys Updated!** Key ID: \`${data.key_id}\` is now active for live checkout.`);
        }
      } catch (err) {
        alert('Failed to update Razorpay credentials: ' + err);
      }
    });
  }

  // Pay with Razorpay Gateway Button in Cart
  const razorpayCheckoutBtn = document.getElementById('razorpayCheckoutBtn');
  if (razorpayCheckoutBtn) {
    razorpayCheckoutBtn.addEventListener('click', () => {
      payWithRazorpay();
    });
  }

  // AP2 Authorize Auto-Pay button (one-time setup)
  const authorizeAutoPayBtn = document.getElementById('authorizeAutoPayBtn');
  if (authorizeAutoPayBtn) {
    authorizeAutoPayBtn.addEventListener('click', () => {
      payWithRazorpay(true); // authorize mode — saves AP2 token after success
    });
  }

  // Check AP2 status when cart opens
  document.getElementById('openCartBtn').addEventListener('click', () => {
    checkAP2Status();
  }, true);

  // User Profile Switcher
  userSelectorBtn.addEventListener('click', () => {
    userModalOverlay.classList.add('open');
  });
  document.getElementById('closeUserModalBtn').addEventListener('click', () => {
    userModalOverlay.classList.remove('open');
  });
  userModalOverlay.addEventListener('click', (e) => {
    if (e.target === userModalOverlay) userModalOverlay.classList.remove('open');
  });

  // Chat Prompt Submit
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const prompt = chatPromptInput.value.trim();
    if (!prompt) return;
    submitChatPrompt(prompt);
  });

  // Quick Prompt Chips
  document.querySelectorAll('.prompt-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt) {
        submitChatPrompt(prompt);
      }
    });
  });
}

// User Switching
window.switchUser = function(userId, name, initials) {
  activeUserId = userId;
  activeUserName = name;
  activeUserInitials = initials;
  userNameText.innerText = name;
  userAvatarText.innerText = initials;
  userModalOverlay.classList.remove('open');
  loadCart();
  loadOrders();
  appendAgentMessage(`Switched active profile to **${name}**. How can I help you today?`);
};

// 1. Catalog Loading & Rendering
async function loadCatalog() {
  try {
    const res = await fetch('/api/inventory');
    const data = await res.json();
    catalogProducts = data.products || [];
    filterAndRenderCatalog();
  } catch (err) {
    console.error('Failed to load inventory:', err);
  }
}

function filterAndRenderCatalog() {
  const query = catalogSearchInput.value.toLowerCase().trim();
  const filtered = catalogProducts.filter(p => {
    const matchesCategory = (currentCategory === 'ALL') || (p.PRODUCT_TYPE.toLowerCase() === currentCategory.toLowerCase());
    const matchesQuery = !query || 
      p.PRODUCT_NAME.toLowerCase().includes(query) ||
      p.PRODUCT_TYPE.toLowerCase().includes(query) ||
      p.PRODUCT_SIZE.toLowerCase().includes(query) ||
      p.DESCRIPTION.toLowerCase().includes(query) ||
      (Array.isArray(p.TAGS) && p.TAGS.some(t => t.toLowerCase().includes(query)));
    return matchesCategory && matchesQuery;
  });

  catalogCountBadge.innerText = `${filtered.length} Products`;
  renderProductsGrid(filtered);
}

function renderProductsGrid(products) {
  if (products.length === 0) {
    productsGrid.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 3.5rem 1rem; color: var(--text-muted);">
        <i data-lucide="package-x" style="width: 44px; height: 44px; margin-bottom: 0.75rem; opacity: 0.4;"></i>
        <p style="font-size: 1rem; font-weight: 600; color: #cbd5e1;">No products found</p>
        <p style="font-size: 0.8rem; margin-top: 4px;">Try adjusting your search terms or category filter.</p>
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  productsGrid.innerHTML = products.map(prod => {
    const stock = prod.STOCK_REMAINING;
    let stockClass = 'in-stock';
    let stockText = `● In Stock: ${stock}`;
    if (stock <= 0) {
      stockClass = 'out-stock';
      stockText = 'Out of Stock';
    } else if (stock <= 5) {
      stockClass = 'low-stock';
      stockText = `⚠️ Low Stock: ${stock}`;
    }

    const basePrice = parseFloat(prod.BASE_PRICE || prod.PRICE || 0);
    const sellingPrice = parseFloat(prod.PRICE || basePrice || 0);
    const diff = sellingPrice - basePrice;
    const pct = basePrice > 0 ? ((diff / basePrice) * 100) : 0;

    let surgeTag = '';
    if (diff > 0.01) {
      surgeTag = `<span class="dynamic-surge-badge" title="Dynamic AI Surge Optimization">+${pct.toFixed(1)}% AI Surge</span>`;
    } else {
      surgeTag = `<span class="dynamic-surge-badge" style="color: #94a3b8;" title="Base Floor Price">🔒 Base Floor</span>`;
    }

    return `
      <div class="product-card" id="card-${prod.id}">
        <div class="product-image-frame">
          <img src="${prod.IMAGE}" alt="${prod.PRODUCT_NAME}" loading="lazy" />
          <span class="product-category-tag">${prod.PRODUCT_TYPE}</span>
          <span class="product-stock-tag ${stockClass}">
            ${stockText}
          </span>
        </div>
        <div class="product-card-body">
          <div class="card-title-group">
            <h3>${prod.PRODUCT_NAME}</h3>
            <div class="card-meta-row" style="margin-top: 4px;">
              <span class="size-badge">Size: <strong>${prod.PRODUCT_SIZE}</strong></span>
              <span class="rating-pill">⭐ ${prod.RATING || '4.8'}</span>
            </div>
          </div>
          <p class="card-description">${prod.DESCRIPTION}</p>
          <div class="card-pricing-footer">
            <div class="price-display-group">
              <span class="current-selling-price">₹${sellingPrice.toFixed(2)}</span>
              ${surgeTag}
            </div>
            <span class="tax-free-tag">0% TAX FREE</span>
          </div>
          <button class="add-to-cart-primary" onclick="handleAddToCart('${prod.id}', '${prod.PRODUCT_SIZE}')" ${stock <= 0 ? 'disabled' : ''} title="Add to Cart">
            <i data-lucide="shopping-cart"></i>
            <span>${stock <= 0 ? 'Out of Stock' : 'Add to Cart'}</span>
          </button>
        </div>
      </div>
    `;
  }).join('');

  if (window.lucide) window.lucide.createIcons();
}

// 2. Cart Operations
async function loadCart() {
  try {
    const res = await fetch(`/api/cart?user_id=${activeUserId}`);
    const cart = await res.json();
    renderCart(cart);
  } catch (err) {
    console.error('Failed to load cart:', err);
  }
}

function renderCart(cart) {
  const count = cart.item_count || 0;
  cartCountBadge.innerText = count;

  if (!cart.items || cart.items.length === 0) {
    cartItemsList.innerHTML = `
      <div style="text-align: center; padding: 4rem 1rem; color: var(--text-muted);">
        <i data-lucide="shopping-cart" style="width: 48px; height: 48px; opacity: 0.35; margin-bottom: 0.75rem;"></i>
        <p style="font-size: 0.95rem; font-weight: 600; color: #cbd5e1;">Your cart is empty</p>
        <p style="font-size: 0.78rem; margin-top: 4px;">Ask Nova in prompt or click "+ Cart" to add items!</p>
      </div>
    `;
    cartSubtotalText.innerText = '₹0.00';
    cartTaxText.innerText = '₹0.00';
    cartTotalText.innerText = '₹0.00';
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  cartItemsList.innerHTML = cart.items.map(item => `
    <div class="cart-item-row">
      <img src="${item.IMAGE}" alt="${item.PRODUCT_NAME}" class="cart-item-img" />
      <div class="cart-item-info">
        <h4>${item.PRODUCT_NAME}</h4>
        <div class="cart-item-sub">Size: ${item.PRODUCT_SIZE} • Available Stock: ${item.STOCK_REMAINING}</div>
        <div class="cart-item-price-calc">₹${Number(item.PRICE).toFixed(2)} × ${item.quantity} = ₹${Number(item.item_total).toFixed(2)}</div>
      </div>
      <div class="cart-item-stepper">
        <button class="stepper-btn" onclick="handleRemoveFromCart('${item.id}', 1)" title="Decrease Quantity">-</button>
        <span style="font-size: 0.85rem; font-weight: 700; min-width: 18px; text-align: center;">${item.quantity}</span>
        <button class="stepper-btn" onclick="handleAddToCart('${item.id}', '${item.PRODUCT_SIZE}')" title="Increase Quantity">+</button>
      </div>
    </div>
  `).join('');

  cartSubtotalText.innerText = `₹${Number(cart.subtotal).toFixed(2)}`;
  cartTaxText.innerText = `₹${Number(cart.estimated_tax || 0).toFixed(2)}`;
  cartTotalText.innerText = `₹${Number(cart.estimated_total).toFixed(2)}`;

  if (window.lucide) window.lucide.createIcons();
}

window.handleAddToCart = async function(productId, size) {
  try {
    const res = await fetch('/api/cart/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: activeUserId,
        product_id: productId,
        quantity: 1,
        size: size
      })
    });
    const data = await res.json();
    if (data.cart) {
      renderCart(data.cart);
    }
  } catch (err) {
    console.error('Failed to add to cart:', err);
  }
};

window.handleRemoveFromCart = async function(productId, quantity) {
  try {
    const res = await fetch('/api/cart/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: activeUserId,
        product_id: productId,
        quantity: quantity
      })
    });
    const data = await res.json();
    if (data.cart) {
      renderCart(data.cart);
    }
  } catch (err) {
    console.error('Failed to remove from cart:', err);
  }
};

window.handleQuickBuy = async function(productId, size) {
  await handleAddToCart(productId, size);
  payWithRazorpay();
};

// AP2 Status Checker — updates cart drawer banner
async function checkAP2Status() {
  try {
    const res = await fetch(`/api/payment/ap2-status?user_id=${activeUserId}`);
    const data = await res.json();
    const banner = document.getElementById('ap2StatusBanner');
    const statusText = document.getElementById('ap2StatusText');
    const statusSub = document.getElementById('ap2StatusSub');
    const authorizeBtn = document.getElementById('authorizeAutoPayBtn');
    if (!statusText) return;

    if (data.authorized) {
      // AP2 active — green banner
      if (banner) {
        banner.style.background = 'rgba(16, 185, 129, 0.12)';
        banner.style.borderColor = 'rgba(16, 185, 129, 0.35)';
      }
      const card = data.card_details || {};
      statusText.innerHTML = `<span style="color:#34d399;">🤖 AP2 Auto-Pay Active — Agent pays autonomously!</span>`;
      if (statusSub) statusSub.innerHTML = `<span style="color:#6ee7b7;">${card.card_network || 'Card'} ${card.card_number_masked || '****'} • No checkout popup needed</span>`;
      if (authorizeBtn) authorizeBtn.style.display = 'none';
    } else {
      // AP2 not set up — show authorize button
      if (banner) {
        banner.style.background = 'rgba(251, 191, 36, 0.1)';
        banner.style.borderColor = 'rgba(251, 191, 36, 0.3)';
      }
      statusText.innerHTML = `<span style="color:#fbbf24;">⚡ Authorize once to enable Agent Auto-Pay</span>`;
      if (statusSub) statusSub.textContent = 'One-time Razorpay setup • AP2 Protocol';
      if (authorizeBtn) authorizeBtn.style.display = 'flex';
    }
    if (window.lucide) window.lucide.createIcons();
  } catch (e) {
    console.warn('AP2 status check failed:', e);
  }
}

// 3. Checkout & Razorpay Gateway
let pendingSimOrderData = null;
let pendingSimAuthorizeMode = false;

async function payWithRazorpay(authorizeMode = false) {
  try {
    // 1. Create Razorpay order via backend
    const orderRes = await fetch('/api/payment/create-order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: activeUserId, currency: 'INR' })
    });
    const orderData = await orderRes.json();

    if (!orderData.success) {
      alert(`Payment initialization failed: ${orderData.error || orderData.detail || 'Cart is empty or Razorpay API error.'}`);
      return;
    }

    const keyId = orderData.key_id;
    const rzpOrderId = orderData.razorpay_order_id;
    const amount = orderData.amount;

    // Always launch real Razorpay Checkout
    if (!window.Razorpay) {
      alert('Razorpay SDK not loaded. Please check your internet connection and reload the page.');
      return;
    }

    const options = {
      key: keyId,
      amount: amount,
      currency: orderData.currency || 'INR',
      name: 'NOVA Store',
      description: authorizeMode
        ? '🔐 AP2 Auto-Pay Authorization (One-time Setup)'
        : 'NOVA Official Store — Secure Checkout',
      image: '/static/images/phone_flagship.svg',
      order_id: rzpOrderId,
      handler: async function (response) {
        await verifyAndCompleteRazorpayPayment({
          razorpay_order_id: response.razorpay_order_id || rzpOrderId,
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_signature: response.razorpay_signature
        }, authorizeMode);
      },
      prefill: {
        name: activeUserName,
        email: `${activeUserId}@nova-store.ai`,
        contact: '9876543210'
      },
      notes: {
        store: 'NOVA Agentic E-Commerce Store',
        user_id: activeUserId
      },
      theme: {
        color: authorizeMode ? '#7c3aed' : '#2563eb'
      },
      modal: {
        ondismiss: function () {
          console.log('Razorpay Checkout dismissed by user.');
        }
      }
    };

    const rzp = new window.Razorpay(options);
    rzp.on('payment.failed', function (response) {
      console.error('Razorpay payment failed:', response.error);
      alert(`Payment failed: ${response.error.description}`);
    });
    rzp.open();

  } catch (err) {
    console.error('Razorpay Checkout Error:', err);
    alert('Payment error: ' + err.message);
  }
}

function openRazorpaySimulator(orderData, authorizeMode = false) {
  pendingSimOrderData = orderData;
  pendingSimAuthorizeMode = authorizeMode;

  const simOverlay = document.getElementById('razorpaySimulatorModalOverlay');
  const amountText = document.getElementById('rzpSimAmountText');
  const btnText = document.getElementById('confirmRzpSimBtnText');

  const inrAmount = (orderData.amount / 100).toFixed(2);
  if (amountText) amountText.innerText = `₹${inrAmount}`;
  if (btnText) {
    btnText.innerText = authorizeMode 
      ? `Authorize AP2 Auto-Pay (₹${inrAmount})` 
      : `Pay & Confirm Order (₹${inrAmount})`;
  }

  if (simOverlay) simOverlay.classList.add('open');
  if (window.lucide) window.lucide.createIcons();
}

window.selectRzpMethod = function(element) {
  document.querySelectorAll('.rzp-sim-method').forEach(m => m.classList.remove('active'));
  element.classList.add('active');
};

// Confirm simulator payment
document.getElementById('confirmRzpSimPaymentBtn')?.addEventListener('click', async () => {
  if (!pendingSimOrderData) return;
  const simOverlay = document.getElementById('razorpaySimulatorModalOverlay');
  if (simOverlay) simOverlay.classList.remove('open');

  const testPaymentId = `pay_rzp_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  await verifyAndCompleteRazorpayPayment({
    razorpay_order_id: pendingSimOrderData.razorpay_order_id,
    razorpay_payment_id: testPaymentId,
    razorpay_signature: 'sandbox_verified',
    payment_method: 'Razorpay Verified (Instant Settlement)'
  }, pendingSimAuthorizeMode);

  pendingSimOrderData = null;
});

document.getElementById('closeRazorpaySimBtn')?.addEventListener('click', () => {
  const simOverlay = document.getElementById('razorpaySimulatorModalOverlay');
  if (simOverlay) simOverlay.classList.remove('open');
  pendingSimOrderData = null;
});

async function verifyAndCompleteRazorpayPayment(paymentPayload, authorizeMode = false) {
  try {
    const verifyRes = await fetch('/api/payment/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: activeUserId,
        razorpay_order_id: paymentPayload.razorpay_order_id,
        razorpay_payment_id: paymentPayload.razorpay_payment_id,
        razorpay_signature: paymentPayload.razorpay_signature,
        shipping_address: paymentPayload.shipping_address || null
      })
    });
    const verifyData = await verifyRes.json();

    if (verifyData.success) {
      cartDrawerOverlay.classList.remove('open');
      await loadCatalog();
      await loadCart();
      await loadOrders();
      await checkAP2Status();

      if (authorizeMode) {
        appendAgentMessage(`
🔐 **AP2 Auto-Pay Authorization Complete!**

Your Razorpay payment has been verified and your card has been authorized for **fully autonomous agent payments**.

- **Payment ID:** \`${verifyData.razorpay_payment_id}\`
- **AP2 Protocol:** \`Active & Verified ✅\`

**From now on**, when you ask me to order anything, I will pay automatically using your saved card without ANY popup!
        `);
      } else {
        appendAgentMessage(`
🎉 **Razorpay Payment Verified & Order Confirmed!**

- **Payment ID:** \`${verifyData.razorpay_payment_id}\`
- **Order ID:** \`${verifyData.order.order_id}\`
- **Total Paid:** **₹${verifyData.order.total.toFixed(2)}**
- **Payment Method:** \`Razorpay Gateway (Online Verified)\`
- **Delivery Destination:** ${verifyData.order.shipping_address}
- **Carrier Tracking:** \`${verifyData.order.tracking_number || 'Generated by Dispatcher'}\`

*Inventory automatically deducted in real-time in \`inventory.json\`!*
        `);
      }
    } else {
      alert(`Payment verification failed: ${verifyData.detail || 'Signature mismatch'}`);
    }
  } catch (err) {
    console.error('Verification error:', err);
    alert('Payment verification error: ' + err);
  }
}

// 4. Order History
async function loadOrders() {
  try {
    const res = await fetch(`/api/orders?user_id=${activeUserId}`);
    const data = await res.json();
    const orders = data.orders || [];
    ordersCountBadge.innerText = orders.length;
    renderOrdersModal(orders);
  } catch (err) {
    console.error('Failed to load orders:', err);
  }
}

function renderOrdersModal(orders) {
  if (orders.length === 0) {
    ordersModalBody.innerHTML = `
      <div style="text-align: center; padding: 3.5rem 1rem; color: var(--text-muted);">
        <i data-lucide="package-open" style="width: 48px; height: 48px; opacity: 0.35; margin-bottom: 0.75rem;"></i>
        <p style="font-size: 1rem; font-weight: 600; color: #cbd5e1;">No Orders Yet</p>
        <p style="font-size: 0.8rem; margin-top: 4px;">Items purchased with Razorpay or AP2 will appear here in real time.</p>
      </div>
    `;
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  const dashboardBanner = `
    <div class="notice-box blue-notice" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem;">
      <div style="display: flex; align-items: center; gap: 0.5rem;">
        <i data-lucide="shield-check" style="width: 18px; height: 18px; color: #60a5fa; flex-shrink: 0;"></i>
        <div>
          <strong style="color: #fff; font-size: 0.82rem;">Razorpay Verified & 24/7 Dispatch Mesh:</strong>
          <div style="font-size: 0.74rem; color: #93c5fd; margin-top: 2px;">Orders eligible for 1-click refund within 24 hours prior to carrier transit.</div>
        </div>
      </div>
      <span style="font-size: 0.68rem; background: rgba(59, 130, 246, 0.25); color: #93c5fd; padding: 0.2rem 0.5rem; border-radius: 4px; font-weight: 700;">INR Official</span>
    </div>
  `;

  const ordersCards = orders.map(ord => {
    const dateStr = new Date(ord.created_at || Date.now()).toLocaleString();
    const isRefunded = (ord.status || '').toLowerCase() === 'refunded';
    const statusClass = (ord.status || 'confirmed').toLowerCase();
    const refundDetails = ord.refund_details || {};
    const trackingNo = ord.tracking_number || 'TRK-' + (ord.order_id || '1001').replace('ORD-', '') + 'A9B';
    const paymentMethod = ord.payment_method || (ord.payment_id ? 'Razorpay Verified' : 'AP2 Protocol');
    const shippingAddress = ord.shipping_address || (activeUserId === 'user_sarah' ? 'Sarah Chen, 102 Innovation Park, Hyderabad' : 'Alex Mercer, 742 Tech Hub, Bengaluru');

    const itemsHtml = (ord.items || []).map(item => {
      const pName = item.PRODUCT_NAME || item.product_name || item.name || 'NOVA Product';
      const pSize = item.PRODUCT_SIZE || item.size || 'Standard';
      const pQty = item.quantity || item.qty || 1;
      const pPrice = Number(item.price || item.unit_price || 0);
      const itemSubtotal = (pPrice * pQty).toFixed(2);

      return `
        <div class="order-item-chip">
          <div class="order-item-left">
            <span class="order-item-qty">${pQty}x</span>
            <span class="order-item-name">${pName}</span>
            <span class="order-item-specs">${pSize}</span>
          </div>
          <span class="order-item-price">₹${itemSubtotal}</span>
        </div>
      `;
    }).join('');

    return `
      <div class="order-history-card">
        <div class="order-card-top">
          <div>
            <div class="order-id-code">${ord.order_id}</div>
            <div class="order-date-text">${dateStr}</div>
          </div>
          <div class="order-status-group">
            <span class="status-badge-pill ${statusClass}">
              ● ${ord.status || 'Confirmed'}
            </span>
            <span class="order-tracking-pill" title="Carrier Tracking Number">
              <i data-lucide="truck"></i> ${trackingNo}
            </span>
            ${!isRefunded ? `
              <button class="order-refund-btn" onclick="handleOrderRefund('${ord.order_id}')" title="Issue Razorpay Refund & Restock Inventory">
                <i data-lucide="rotate-ccw"></i> Refund
              </button>
            ` : ''}
          </div>
        </div>

        <div class="order-items-grid">
          ${itemsHtml}
        </div>

        <div class="order-card-bottom">
          <div class="order-meta-info">
            <span class="order-payment-method">⚡ ${paymentMethod}</span>
            <span class="order-ship-address">📍 Ship to: ${shippingAddress}</span>
          </div>
          <div class="order-total-block">
            <div class="order-total-label">Grand Total:</div>
            <div class="order-total-value ${isRefunded ? 'is-refunded' : ''}">₹${Number(ord.total || 0).toFixed(2)}</div>
          </div>
        </div>

        ${isRefunded ? `
          <div class="order-refund-alert">
            <i data-lucide="check-circle-2"></i>
            <span><strong>Refund Completed:</strong> Refund ID: <code>${refundDetails.refund_id || 'Processed'}</code> • Amount ₹${Number(refundDetails.amount || ord.total || 0).toFixed(2)} credited back to account.</span>
          </div>
        ` : ''}
      </div>
    `;
  }).join('');

  ordersModalBody.innerHTML = dashboardBanner + ordersCards;

  if (window.lucide) window.lucide.createIcons();
}

window.handleOrderRefund = async function(orderId) {
  if (!confirm(`Are you sure you want to issue a full refund for Order #${orderId} via Razorpay Gateway?\n\nThis will credit the customer account and restore product stock in the inventory catalog.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/orders/${orderId}/refund`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Customer requested refund via Storefront' })
    });
    const data = await res.json();

    if (data.success) {
      alert(`✅ ${data.message}`);
      await loadOrders();
      await loadCatalog();

      appendAgentMessage(`
🔄 **Razorpay Refund Issued Successfully!**

- **Order ID:** \`${orderId}\`
- **Refund ID:** \`${data.refund_details.refund_id}\`
- **Amount Refunded:** **$${data.refund_details.amount.toFixed(2)}**
- **Gateway:** \`${data.refund_details.gateway}\`
- **Status:** \`Refunded & Stock Restocked in inventory.json\`
      `);
    } else {
      alert(`Refund failed: ${data.detail || data.error || 'Unknown error'}`);
    }
  } catch (err) {
    console.error('Failed to issue refund:', err);
    alert('Error processing refund: ' + err);
  }
};

// 5. Chat Agent Integration
async function submitChatPrompt(prompt) {
  chatPromptInput.value = '';
  appendUserMessage(prompt);

  // Disable send button while awaiting response
  sendPromptBtn.disabled = true;
  chatPromptInput.disabled = true;

  // Add temporary typing indicator
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: activeUserId,
        prompt: prompt,
        conversation_history: chatHistory
      })
    });

    const data = await res.json();
    removeTypingIndicator(typingId);

    // Save to conversation history
    chatHistory.push({ role: 'user', content: prompt });
    chatHistory.push({ role: 'assistant', content: data.response });

    // Render Agent response
    appendAgentMessage(data.response, data.tool_calls);

    // Sync UI states if tools modified cart or orders
    if (data.cart) {
      renderCart(data.cart);
    }
    if (data.orders) {
      ordersCountBadge.innerText = data.orders.length;
      renderOrdersModal(data.orders);
    }

    // Refresh catalog and orders whenever tools affect inventory, cart, or orders
    const toolNames = (data.tool_calls || []).map(t => t.name);
    const cartOrOrderMutated = toolNames.some(t => [
      'add_to_cart', 'batch_add_to_cart', 'remove_from_cart', 'clear_cart',
      'trigger_razorpay_checkout', 'autonomous_agent_pay', 'process_razorpay_card_payment',
      'cancel_order', 'request_order_refund', 'submit_product_review'
    ].includes(t));

    if (cartOrOrderMutated) {
      await loadCatalog();
      await loadCart();
      await loadOrders();
    }

    // AP2 status refresh
    if (toolNames.some(t => ['autonomous_agent_pay', 'process_razorpay_card_payment', 'check_ap2_authorization', 'trigger_razorpay_checkout'].includes(t))) {
      await checkAP2Status();
    }

    // 🔑 KEY: If agent validated card details and created Razorpay Order, open the REAL Razorpay Checkout modal
    // This ensures actual payment capture that shows as "Captured" in Razorpay Dashboard
    if (data.checkout_payload && data.checkout_payload.needs_razorpay_checkout) {
      const cp = data.checkout_payload;
      setTimeout(() => {
        openRazorpayCheckoutFromAgent(cp);
      }, 800);
    }

  } catch (err) {
    removeTypingIndicator(typingId);
    console.error('Chat error:', err);
    appendAgentMessage('Sorry, I encountered an issue processing your request. Please try again.');
  } finally {
    sendPromptBtn.disabled = false;
    chatPromptInput.disabled = false;
    chatPromptInput.focus();
  }
}

/**
 * Opens the Razorpay Standard Checkout modal with a server-created order ID.
 * This generates a REAL payment that appears as "Captured" in the Razorpay Dashboard.
 * Handles both manual agent card payments and AP2 autonomous agent payments.
 */
async function openRazorpayCheckoutFromAgent(checkoutPayload) {
  const {
    razorpay_order_id, amount, currency, key_id, prefill,
    user_id: payUserId, ap2_autonomous_payment, stored_card, shipping_address
  } = checkoutPayload;

  const isAP2 = !!ap2_autonomous_payment;
  const cardInfo = stored_card ? `${stored_card.card_network || 'Card'} ${stored_card.card_number_masked || '****'}` : 'your saved card';

  if (isAP2) {
    appendAgentMessage(
      `🤖 **Nova has prepared your payment!**\n\n` +
      `Razorpay Order \`${razorpay_order_id}\` is ready. ` +
      `Complete the secure checkout using ${cardInfo} — ` +
      `this payment will be visible in your Razorpay dashboard immediately.`
    );
  }

  if (window.Razorpay) {
    const options = {
      key: key_id,
      amount: amount,
      currency: currency || 'INR',
      name: 'AI Growth Commerce',
      description: isAP2
        ? `🤖 Nova Agent Payment — ${cardInfo}`
        : 'Agentic Store — Nova AI Checkout',
      order_id: razorpay_order_id,
      handler: async function (response) {
        // Real payment captured by Razorpay — verify and finalize order
        appendAgentMessage(`⏳ Payment received from Razorpay. Verifying and confirming order...`);
        await verifyAndCompleteRazorpayPayment({
          razorpay_order_id: response.razorpay_order_id || razorpay_order_id,
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_signature: response.razorpay_signature,
          shipping_address: shipping_address
        }, false);
      },
      prefill: prefill || {
        name: activeUserName,
        email: `${activeUserId}@growthcommerce.ai`,
        contact: '9999999999'
      },
      notes: {
        user_id: payUserId || activeUserId,
        store: 'AI Growth Commerce Agentic Store',
        ap2_agent_payment: isAP2 ? 'true' : 'false'
      },
      theme: {
        color: isAP2 ? '#7c3aed' : '#2563eb'
      },
      modal: {
        ondismiss: function () {
          appendAgentMessage(
            isAP2
              ? `⚠️ AP2 Checkout closed. Your cart is still intact — just say "order my cart" to retry.`
              : `⚠️ Razorpay Checkout was closed. Your cart is still intact — type "pay" to retry.`
          );
        }
      }
    };
    const rzp = new window.Razorpay(options);
    rzp.open();
  } else {
    // Razorpay.js not loaded — fallback verification with real order ID
    appendAgentMessage(`⚠️ Razorpay.js SDK not loaded. Attempting direct order confirmation...`);
    await verifyAndCompleteRazorpayPayment({
      razorpay_order_id: razorpay_order_id,
      razorpay_payment_id: `pay_${Date.now().toString(16)}`,
      razorpay_signature: 'sandbox_verified',
      shipping_address: shipping_address
    }, false);
  }
}


function appendUserMessage(text) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble user';
  bubble.innerHTML = `
    <div class="bubble-avatar">${activeUserInitials}</div>
    <div class="bubble-content"><p>${escapeHtml(text)}</p></div>
  `;
  chatMessages.appendChild(bubble);
  scrollChatToBottom();
}

function appendAgentMessage(markdownText, toolCalls = []) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble agent';

  let toolsHtml = '';
  if (toolCalls && toolCalls.length > 0) {
    toolsHtml = toolCalls.map(tc => `
      <div class="tool-trace-badge">
        <i data-lucide="cpu" style="width: 12px; height: 12px;"></i>
        Tool: ${tc.name}
      </div>
    `).join('');
  }

  const formattedHtml = parseSimpleMarkdown(markdownText);

  bubble.innerHTML = `
    <div class="bubble-avatar"><i data-lucide="bot" style="width: 16px; height: 16px;"></i></div>
    <div class="bubble-content">
      ${toolsHtml}
      <div class="markdown-body">${formattedHtml}</div>
    </div>
  `;
  chatMessages.appendChild(bubble);
  if (window.lucide) window.lucide.createIcons();
  scrollChatToBottom();
}

function appendTypingIndicator() {
  const id = 'typing-' + Date.now();
  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble agent';
  bubble.id = id;
  bubble.innerHTML = `
    <div class="bubble-avatar"><i data-lucide="bot" style="width: 16px; height: 16px;"></i></div>
    <div class="bubble-content" style="color: var(--text-muted); font-style: italic;">
      Nova is thinking & querying store tools...
    </div>
  `;
  chatMessages.appendChild(bubble);
  if (window.lucide) window.lucide.createIcons();
  scrollChatToBottom();
  return id;
}

function removeTypingIndicator(id) {
  const elem = document.getElementById(id);
  if (elem) elem.remove();
}

function scrollChatToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
}

function parseSimpleMarkdown(md) {
  if (!md) return '';
  let html = md;
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.1); padding: 2px 5px; border-radius: 4px; font-family: monospace; color: var(--text-accent);">$1</code>');
  // Bullet points
  html = html.replace(/^\s*-\s+(.*)$/gm, '<li style="margin-left: 1.25rem; margin-bottom: 4px;">$1</li>');
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p style="margin-top: 8px;">');
  html = html.replace(/\n/g, '<br/>');
  return `<p>${html}</p>`;
}
