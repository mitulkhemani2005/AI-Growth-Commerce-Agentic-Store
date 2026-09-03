import React from 'react';
import { 
  ClipboardList, 
  Truck, 
  RotateCcw, 
  CheckCircle, 
  Clock, 
  Package, 
  AlertCircle 
} from 'lucide-react';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import Modal from '../shared/Modal';

export default function OrdersModal() {
  const { 
    orders, 
    isOrdersOpen, 
    setIsOrdersOpen, 
    refreshOrders, 
    refreshCart, 
    refreshCatalog,
    showToast 
  } = useStore();

  const handleRefund = async (orderId) => {
    if (!window.confirm(`Issue Razorpay refund for order ${orderId}? This will also restore inventory stock.`)) {
      return;
    }
    try {
      const res = await api.refundOrder(orderId, 'Customer Request (24h Policy)');
      if (res.success) {
        showToast(`Refund processed successfully for ${orderId}!`, 'success');
        await Promise.all([refreshOrders(), refreshCart(), refreshCatalog()]);
      } else {
        showToast(`Refund failed: ${res.error || 'Policy restriction'}`, 'error');
      }
    } catch (e) {
      showToast(e.message, 'error');
    }
  };

  return (
    <Modal 
      isOpen={isOrdersOpen} 
      onClose={() => setIsOrdersOpen(false)}
      title={`Order History & Real-Time Tracking (${orders.length})`}
      icon={ClipboardList}
      maxWidth="780px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {/* Notice Banner */}
        <div style={{
          background: 'rgba(59, 130, 246, 0.1)',
          border: '1px solid rgba(59, 130, 246, 0.25)',
          borderRadius: '10px',
          padding: '0.75rem 1rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.82rem'
        }}>
          <div>
            <strong style={{ color: '#fff' }}>Razorpay Verified & 24/7 Logistics Mesh</strong>
            <p style={{ color: '#93c5fd', fontSize: '0.74rem' }}>
              Orders are eligible for automated 1-click refund within 24 hours prior to dispatch carrier transit.
            </p>
          </div>
          <span style={{ background: 'rgba(59, 130, 246, 0.25)', color: '#93c5fd', padding: '0.2rem 0.6rem', borderRadius: '4px', fontWeight: 700, fontSize: '0.72rem' }}>
            INR Official
          </span>
        </div>

        {/* Orders List */}
        {orders.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3.5rem 1rem', color: '#94a3b8' }}>
            <Package size={44} style={{ opacity: 0.35, margin: '0 auto 0.75rem' }} />
            <h4 style={{ color: '#fff', fontSize: '1rem' }}>No orders found</h4>
            <p style={{ fontSize: '0.8rem', marginTop: '4px' }}>Items ordered via Razorpay or AP2 will appear here in real time.</p>
          </div>
        ) : (
          orders.map((ord) => {
            const dateStr = new Date(ord.created_at || Date.now()).toLocaleString();
            const status = (ord.status || 'Confirmed').toLowerCase();
            const isRefunded = status === 'refunded' || status === 'cancelled';
            const tracking = ord.tracking_number || `TRK-${(ord.order_id || '1001').replace('ORD-', '')}X9`;

            // Stages
            const stages = ['Pending', 'Confirmed', 'Dispatched', 'Shipped', 'Delivered'];
            const currentIdx = stages.findIndex(s => s.toLowerCase() === status);

            return (
              <div 
                key={ord.order_id} 
                style={{
                  background: 'rgba(19, 31, 56, 0.5)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '12px',
                  padding: '1.25rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.85rem'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: '0.95rem', color: '#fff' }}>
                      {ord.order_id}
                    </span>
                    <div style={{ fontSize: '0.74rem', color: '#94a3b8', marginTop: '2px' }}>
                      {dateStr}
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                    <span style={{
                      fontSize: '0.74rem',
                      fontWeight: 700,
                      padding: '0.2rem 0.6rem',
                      borderRadius: '9999px',
                      background: isRefunded ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                      color: isRefunded ? '#fb7185' : '#34d399',
                      border: `1px solid ${isRefunded ? 'rgba(244, 63, 94, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`
                    }}>
                      ● {ord.status || 'Confirmed'}
                    </span>

                    <span style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      fontSize: '0.72rem',
                      fontFamily: 'monospace',
                      background: 'rgba(255, 255, 255, 0.05)',
                      color: '#94a3b8',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px'
                    }}>
                      <Truck size={12} />
                      <span>{tracking}</span>
                    </span>

                    {!isRefunded && (
                      <button 
                        onClick={() => handleRefund(ord.order_id)}
                        className="action-btn"
                        style={{ padding: '0.25rem 0.6rem', fontSize: '0.74rem', color: '#fb7185' }}
                        title="Evaluate 24-Hour Cancellation & Refund Rule"
                      >
                        <RotateCcw size={12} />
                        <span>Refund</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Progress Pipeline */}
                {!isRefunded && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', margin: '0.35rem 0' }}>
                    {stages.map((stage, sIdx) => {
                      const isReached = currentIdx >= sIdx;
                      return (
                        <React.Fragment key={stage}>
                          <div style={{
                            flex: 1,
                            height: '4px',
                            background: isReached ? '#10b981' : 'rgba(255, 255, 255, 0.1)',
                            borderRadius: '2px',
                            transition: 'all 0.3s'
                          }} />
                          <span style={{
                            fontSize: '0.66rem',
                            fontWeight: 700,
                            color: isReached ? '#34d399' : '#64748b'
                          }}>
                            {stage}
                          </span>
                        </React.Fragment>
                      );
                    })}
                  </div>
                )}

                {/* Items */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  {(ord.items || []).map((it, idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', color: '#cbd5e1' }}>
                      <span>{it.quantity || 1}x {it.PRODUCT_NAME || it.name || 'Device'} ({it.PRODUCT_SIZE || 'Standard'})</span>
                      <span style={{ fontFamily: 'monospace' }}>₹{(Number(it.price || it.PRICE || 0) * Number(it.quantity || 1)).toFixed(2)}</span>
                    </div>
                  ))}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255, 255, 255, 0.06)', paddingTop: '0.65rem' }}>
                  <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                    {ord.payment_method || 'Razorpay Gateway Verified'} • Ship to: {ord.shipping_address || 'Customer Address'}
                  </span>
                  <div style={{ fontSize: '1rem', fontWeight: 800, fontFamily: 'monospace', color: '#fff' }}>
                    Total: ₹{Number(ord.total || 0).toFixed(2)}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </Modal>
  );
}
