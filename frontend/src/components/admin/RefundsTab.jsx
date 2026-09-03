import React from 'react';
import { RotateCcw, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';

export default function RefundsTab() {
  const { adminOrders, loadAllAdminData } = useAdmin();
  const { refreshCatalog, showToast } = useStore();

  const handleCancelOrder = async (orderId, force = false) => {
    const confirmMsg = force 
      ? `Force Store Owner override refund for order ${orderId}?` 
      : `Process standard 24-hour refund for order ${orderId}?`;

    if (!window.confirm(confirmMsg)) return;

    try {
      const res = await api.adminCancelOrder(orderId, 'Store Owner Admin Evaluation', force);
      if (res.success) {
        showToast(res.message || `Order ${orderId} refunded and inventory restocked!`, 'success');
        await Promise.all([loadAllAdminData(), refreshCatalog()]);
      } else {
        showToast(res.error || 'Refund evaluation failed', 'error');
      }
    } catch (e) {
      showToast(e.message, 'error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
          Refunds & 24h Policy Governance Engine
        </h2>
        <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
          Strict Rule: Orders cancelled <strong>within 24 hours</strong> of creation AND <strong>not yet shipped</strong> are auto-approved for Razorpay refund + automated inventory restock.
        </p>
      </div>

      <div className="glass-panel">
        <div className="admin-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Order ID</th>
                <th>Order Date</th>
                <th>Age (Hours)</th>
                <th>Status</th>
                <th>24h & Non-Shipped Policy</th>
                <th>Total (₹)</th>
                <th>Refund Action</th>
              </tr>
            </thead>
            <tbody>
              {adminOrders.map((ord) => {
                const date = new Date(ord.created_at || Date.now());
                const ageHours = ((Date.now() - date.getTime()) / (1000 * 3600)).toFixed(1);
                const status = (ord.status || 'Confirmed').toLowerCase();
                const isShipped = status === 'shipped' || status === 'delivered';
                const isRefunded = status === 'refunded' || status === 'cancelled';
                const isEligible = parseFloat(ageHours) <= 24.0 && !isShipped && !isRefunded;

                return (
                  <tr key={ord.order_id}>
                    <td>
                      <strong style={{ fontFamily: 'monospace', color: '#fff' }}>{ord.order_id}</strong>
                    </td>
                    <td style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                      {date.toLocaleString()}
                    </td>
                    <td style={{ fontFamily: 'monospace', color: parseFloat(ageHours) <= 24 ? '#34d399' : '#fb7185' }}>
                      {ageHours} hrs
                    </td>
                    <td>
                      <span style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '0.15rem 0.5rem',
                        borderRadius: '9999px',
                        background: isRefunded ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                        color: isRefunded ? '#fb7185' : '#34d399'
                      }}>
                        {ord.status || 'Confirmed'}
                      </span>
                    </td>
                    <td>
                      {isRefunded ? (
                        <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Refund Completed</span>
                      ) : isEligible ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#34d399', fontSize: '0.75rem', fontWeight: 700 }}>
                          <CheckCircle2 size={13} />
                          <span>Eligible for Auto-Refund (&le;24h)</span>
                        </span>
                      ) : (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#fb7185', fontSize: '0.75rem' }}>
                          <XCircle size={13} />
                          <span>Restricted ({isShipped ? 'In Transit' : '>24h Old'})</span>
                        </span>
                      )}
                    </td>
                    <td style={{ fontFamily: 'monospace', fontWeight: 800, color: '#fff' }}>
                      ₹{Number(ord.total || 0).toFixed(2)}
                    </td>
                    <td>
                      {!isRefunded ? (
                        <div style={{ display: 'flex', gap: '0.4rem' }}>
                          <button 
                            className="action-btn"
                            style={{ 
                              padding: '0.2rem 0.55rem', 
                              fontSize: '0.72rem',
                              color: isEligible ? '#34d399' : '#fb7185'
                            }}
                            onClick={() => handleCancelOrder(ord.order_id, false)}
                          >
                            <RotateCcw size={11} />
                            <span>Auto-Evaluate</span>
                          </button>

                          <button 
                            className="action-btn"
                            style={{ padding: '0.2rem 0.55rem', fontSize: '0.72rem', color: '#f59e0b' }}
                            onClick={() => handleCancelOrder(ord.order_id, true)}
                            title="Force Store Owner Override"
                          >
                            <span>Force</span>
                          </button>
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.72rem', color: '#64748b' }}>Settled</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
