import React, { useState, useEffect } from 'react';
import { X, Trash2, ShieldCheck, ShieldAlert, CreditCard, Lock, Zap } from 'lucide-react';
import confetti from 'canvas-confetti';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import { loadPaymentSdk } from '../../api/paymentSdk';

export default function CartDrawer() {
  const {
    currentUser,
    serviceStatus,
    cart,
    isCartOpen,
    setIsCartOpen,
    addToCart,
    removeFromCart,
    ap2Status,
    refreshAP2Status,
    refreshCart,
    refreshOrders,
    refreshCatalog,
    showToast
  } = useStore();

  const [isCheckingOut, setIsCheckingOut] = useState(false);
  const [simModalData, setSimModalData] = useState(null);
  const [crossSells, setCrossSells] = useState([]);

  useEffect(() => {
    if (isCartOpen) {
      api.getCartCrossSells(currentUser.id)
        .then(res => {
          if (res && res.recommendations) setCrossSells(res.recommendations);
        })
        .catch(() => {});
    }
  }, [isCartOpen, cart?.items?.length, currentUser.id]);

  if (!isCartOpen) return null;

  const items = cart?.items || [];
  const subtotal = Number(cart?.subtotal || 0);
  const total = Number(cart?.estimated_total || subtotal);

  const handleAP2DirectPay = async () => {
    if (items.length === 0) {
      showToast('Your bag is empty.', 'error');
      return;
    }

    setIsCheckingOut(true);
    try {
      const res = await api.conversationalCheckout({
        user_id: currentUser.id,
        payment_method: 'AP2',
        shipping_address: currentUser.address
      });

      if (res.success) {
        try {
          confetti({
            particleCount: 80,
            spread: 60,
            origin: { y: 0.6 }
          });
        } catch (e) {}

        setIsCartOpen(false);
        await Promise.all([
          refreshCart(),
          refreshOrders(),
          refreshCatalog(),
          refreshAP2Status()
        ]);

        showToast(`🎉 Order Placed via AP2 Protocol! (ID: ${res.order_id})`, 'success');
      } else {
        showToast(res.error || 'AP2 Direct Checkout Failed', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsCheckingOut(false);
    }
  };


  const handleRazorpayPay = async (isAuthorizeMode = false) => {
    if (items.length === 0) {
      showToast('Your bag is empty.', 'error');
      return;
    }

    setIsCheckingOut(true);
    try {
      const orderData = await api.createRazorpayOrder(currentUser.id, 'INR');
      if (!orderData.success) {
        throw new Error(orderData.error || 'Payment initialization failed.');
      }

      if (!orderData.is_sandbox) await loadPaymentSdk();
      if (orderData.is_sandbox) {
        setSimModalData({ orderData, isAuthorizeMode });
      } else if (window.Razorpay) {
        const options = {
          key: orderData.key_id,
          amount: orderData.amount,
          currency: orderData.currency || 'INR',
          name: 'Nova',
          description: isAuthorizeMode
            ? '🔐 AP2 Auto-Pay Spending Mandate Authorization'
            : 'Order Checkout • 0% Tax Standard Settlement',
          image: '/static/images/phone_flagship.svg',
          order_id: orderData.razorpay_order_id,
          handler: async function (response) {
            await finalizePayment({
              razorpay_order_id: response.razorpay_order_id || orderData.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
              shipping_address: currentUser.address
            }, isAuthorizeMode);
          },
          prefill: {
            name: currentUser.name,
            email: currentUser.email,
            contact: '9876543210'
          },
          theme: {
            color: '#111111'
          },
          modal: {
            ondismiss: () => setIsCheckingOut(false)
          }
        };

        const rzp = new window.Razorpay(options);
        rzp.on('payment.failed', (res) => {
          setIsCheckingOut(false);
          showToast(`Payment failed: ${res.error?.description || 'Declined'}`, 'error');
        });
        rzp.open();
      } else {
        throw new Error('Razorpay checkout could not load. Please check your connection and retry.');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsCheckingOut(false);
    }
  };

  const finalizePayment = async (payload, isAuthorizeMode = false) => {
    if (isCheckingOut) return;
    setIsCheckingOut(true);
    try {
      const verifyRes = await api.verifyRazorpayPayment({
        user_id: currentUser.id,
        ...payload
      });

      if (verifyRes.success) {
        try {
          confetti({
            particleCount: 80,
            spread: 60,
            origin: { y: 0.6 }
          });
        } catch (e) {}

        setIsCartOpen(false);
        setSimModalData(null);
        await Promise.all([
          refreshCart(),
          refreshOrders(),
          refreshCatalog(),
          refreshAP2Status()
        ]);

        showToast(
          isAuthorizeMode
            ? '🔐 AP2 Mandate verified! Agent Nova can now place future orders automatically.'
            : `🎉 Order Confirmed! Payment ID: ${verifyRes.razorpay_payment_id}`,
          'success'
        );
      }
    } catch (err) {
      showToast(`Verification error: ${err.message}`, 'error');
    } finally {
      setIsCheckingOut(false);
    }
  };

  return (
    <>
      <div className="nike-bag-backdrop" onClick={() => setIsCartOpen(false)}>
        <div className="nike-bag-panel" onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <div className="bag-header-row">
            <h3 className="bag-header-title">BAG ({cart?.item_count || 0})</h3>
            <button
              className="nike-icon-btn"
              onClick={() => setIsCartOpen(false)}
              title="Close Bag"
            >
              <X size={20} />
            </button>
          </div>

          {/* Free Shipping Indicator */}
          <div className="free-shipping-meter">
            <span style={{ color: '#2e7d32' }}>⚡ Free Delivery on All Orders</span>
            <span style={{ color: '#707072' }}>• 0% Tax Storewide</span>
          </div>

          {/* Items */}
          <div className="bag-items-list">
            {items.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '4rem 1rem', color: 'var(--text-muted)' }}>
                <h4 style={{ fontFamily: 'var(--font-display)', fontSize: '1.6rem', color: 'var(--text-bright)', textTransform: 'uppercase' }}>
                  Your Bag is Empty
                </h4>
                <p style={{ fontSize: '0.85rem', marginTop: '0.35rem', color: 'var(--text-secondary)' }}>
                  Explore trending drops or ask Nova Copilot to discover hardware for you.
                </p>
              </div>
            ) : (
              items.map((item) => {

                return (
                  <div key={item.id} className="bag-item-card">
                    <div className="bag-item-thumb">
                      <img src={item.IMAGE} alt={item.PRODUCT_NAME} />
                    </div>

                    <div className="bag-item-details">
                      <h5 className="bag-item-title">{item.PRODUCT_NAME}</h5>
                      <span className="bag-item-cat">{item.PRODUCT_TYPE} • {item.PRODUCT_SIZE || 'Standard'}</span>
                      <div className="bag-item-price">MRP : ₹{Number(item.PRICE).toFixed(2)}</div>

                      <div className="bag-stepper-row">
                        <button
                          className="bag-qty-btn"
                          onClick={() => removeFromCart(item.id, 1).catch(() => {})}
                        >
                          -
                        </button>
                        <span style={{ fontSize: '0.88rem', fontWeight: 800, minWidth: '20px', textAlign: 'center' }}>
                          {item.quantity}
                        </span>
                        <button
                          className="bag-qty-btn"
                          onClick={() => addToCart(item.id, item.PRODUCT_SIZE).catch(() => {})}
                        >
                          +
                        </button>

                        <button
                          onClick={() => removeFromCart(item.id, item.quantity).catch(() => {})}
                          style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                          title="Remove item"
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            )}

            {/* Cross-Sell Recommendations */}
            {items.length > 0 && crossSells.length > 0 && (
              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: '0.74rem', fontWeight: 800, color: 'var(--cyber-cyan)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                  Recommended accessories
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.65rem' }}>
                  {crossSells.map((rec) => (
                    <div
                      key={rec.product_id}
                      style={{
                        background: 'rgba(255, 255, 255, 0.03)',
                        border: '1px solid var(--border-glass)',
                        borderRadius: '8px',
                        padding: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '0.75rem'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                        <img
                          src={rec.image || '/static/images/phone_flagship.svg'}
                          alt={rec.product_name}
                          style={{ width: '40px', height: '40px', objectFit: 'contain' }}
                        />
                        <div>
                          <strong style={{ fontSize: '0.84rem', color: 'var(--text-bright)', display: 'block' }}>{rec.product_name}</strong>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{rec.rationale}</span>
                          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--neon-emerald)' }}>
                            ₹{Number(rec.original_price).toFixed(2)}
                          </div>
                        </div>
                      </div>

                      <button
                        className="nike-pill-btn secondary-white"
                        style={{ padding: '0.35rem 0.85rem', fontSize: '0.75rem' }}
                        onClick={() => addToCart(rec.product_id).catch(() => {})}
                      >
                        + Add
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>


          {/* Footer & Checkout */}
          <div className="bag-footer-checkout">
            {/* AP2 Status Mini Box */}
            <div style={{
              background: ap2Status?.authorized ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
              border: `1px solid ${ap2Status?.authorized ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
              borderRadius: '8px',
              padding: '0.75rem 1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              fontSize: '0.8rem'
            }}>
              {ap2Status?.authorized ? (
                <ShieldCheck size={18} style={{ color: 'var(--neon-emerald)', flexShrink: 0 }} />
              ) : (
                <ShieldAlert size={18} style={{ color: 'var(--solar-amber)', flexShrink: 0 }} />
              )}
              <div>
                <strong style={{ color: 'var(--text-bright)' }}>
                  {ap2Status?.authorized ? 'AP2 Auto-Pay Protocol Active' : 'AP2 Auto-Pay Available'}
                </strong>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>
                  {ap2Status?.authorized ? 'Agent Nova can checkout without modal popups' : 'Authorize once to enable autonomous AI payments'}
                </div>
              </div>
            </div>

            <div className="bag-summary-line">
              <span>Subtotal</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>₹{subtotal.toFixed(2)}</span>
            </div>
            <div className="bag-summary-line">
              <span>Estimated Delivery</span>
              <span style={{ color: '#2e7d32', fontWeight: 700 }}>Free</span>
            </div>
            <div className="bag-summary-line">
              <span>Taxes (0% Storewide Policy)</span>
              <span>₹0.00</span>
            </div>

            <div className="bag-summary-line total">
              <span>Total</span>
              <span style={{ fontFamily: 'monospace' }}>₹{total.toFixed(2)}</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem', marginTop: '0.5rem' }}>
              {ap2Status?.authorized && items.length > 0 && (
                <button
                  className="nike-pill-btn accent-volt"
                  style={{ width: '100%', color: '#111', fontWeight: 800, justifyContent: 'center' }}
                  onClick={handleAP2DirectPay}
                  disabled={isCheckingOut}
                >
                  <Zap size={16} />
                  <span>{isCheckingOut ? 'Settling AP2 Mandate...' : '1-Click AP2 Instant Checkout'}</span>
                </button>
              )}

              {serviceStatus?.payment_mode === 'demo' && !ap2Status?.authorized && items.length > 0 && (
                <button
                  className="nike-pill-btn secondary-white"
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => handleRazorpayPay(true)}
                  disabled={isCheckingOut}
                >
                  <Lock size={15} />
                  <span>Authorize AP2 Auto-Pay</span>
                </button>
              )}

              <button
                className="nike-pill-btn primary-black"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => handleRazorpayPay(false)}
                disabled={items.length === 0 || isCheckingOut}
              >
                <CreditCard size={17} />
                <span>{isCheckingOut ? 'Opening Gateway...' : (serviceStatus?.payment_mode === 'demo' ? 'Demo checkout' : 'Secure checkout')}</span>
              </button>
            </div>

          </div>
        </div>
      </div>

      {/* Simulator Modal Fallback */}
      {simModalData && (
        <div className="nike-bag-backdrop" onClick={() => setSimModalData(null)}>
          <div className="modal-content-box" style={{ maxWidth: '420px', background: '#fff', color: '#111', margin: 'auto' }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header" style={{ borderColor: '#e5e5e5' }}>
              <h3 style={{ color: '#111', fontFamily: 'var(--font-display)', textTransform: 'uppercase' }}>
                Nova Demo Checkout
              </h3>
              <button className="drawer-close-btn" onClick={() => setSimModalData(null)}>
                <X size={18} />
              </button>
            </div>
            <div className="modal-body" style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '0.85rem', color: '#707072' }}>Total Payable:</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '2.5rem', fontWeight: 900, color: '#111' }}>
                ₹{(simModalData.orderData.amount / 100).toFixed(2)}
              </div>
              <span style={{ fontSize: '0.72rem', background: '#f5f5f5', color: '#111', padding: '0.2rem 0.6rem', borderRadius: '9999px', fontWeight: 700 }}>
                Demo only • No money is charged
              </span>

              <button
                className="nike-pill-btn primary-black"
                disabled={isCheckingOut}
                style={{ width: '100%', marginTop: '1.5rem' }}
                onClick={() => finalizePayment({
                  razorpay_order_id: simModalData.orderData.razorpay_order_id,
                  razorpay_payment_id: `pay_demo_${Date.now()}`,
                  razorpay_signature: 'sandbox_verified'
                }, simModalData.isAuthorizeMode)}
              >
                Complete Payment
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
