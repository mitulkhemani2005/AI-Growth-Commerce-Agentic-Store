import React, { useState } from 'react';
import { ShoppingCart, Truck, CheckCircle2, RotateCcw } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { api } from '../../api/client';

export default function OrdersTab() {
  const { adminOrders, loadAllAdminData } = useAdmin();
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [updatingId, setUpdatingId] = useState(null);

  const filteredOrders = adminOrders.filter(ord => {
    if (statusFilter === 'ALL') return true;
    return (ord.status || '').toLowerCase() === statusFilter.toLowerCase();
  });

  const handleUpdateStatus = async (orderId, newStatus) => {
    setUpdatingId(orderId);
    try {
      await api.adminUpdateOrderStatus(orderId, newStatus);
      await loadAllAdminData();
    } catch (e) {
      alert(`Failed to update status: ${e.message}`);
    } finally {
      setUpdatingId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            Orders & Dispatch Pipeline ({filteredOrders.length})
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            Lifecycle state transitions: <code>Pending</code> ➔ <code>Confirmed</code> (Stock Deducted) ➔ <code>Dispatched</code> ➔ <code>Shipped</code> ➔ <code>Delivered</code>.
          </p>
        </div>

        <select 
          className="form-select"
          style={{ width: '180px' }}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="ALL">All Statuses</option>
          <option value="Pending">Pending</option>
          <option value="Confirmed">Confirmed</option>
          <option value="Dispatched">Dispatched</option>
          <option value="Shipped">Shipped</option>
          <option value="Delivered">Delivered</option>
          <option value="Cancelled">Cancelled</option>
          <option value="Refunded">Refunded</option>
        </select>
      </div>

      <div className="glass-panel">
        <div className="admin-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Order ID & Date</th>
                <th>Customer</th>
                <th>Items Purchased</th>
                <th>Total (₹)</th>
                <th>Tracking #</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredOrders.length === 0 ? (
                <tr>
                  <td colSpan="7" style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
                    No orders matching selected status filter.
                  </td>
                </tr>
              ) : (
                filteredOrders.map((ord) => {
                  const dateStr = new Date(ord.created_at || Date.now()).toLocaleDateString();
                  const status = (ord.status || 'Confirmed').toLowerCase();
                  const isDelivered = status === 'delivered';
                  const isRefunded = status === 'refunded' || status === 'cancelled';

                  return (
                    <tr key={ord.order_id}>
                      <td>
                        <strong style={{ color: '#fff', fontFamily: 'monospace' }}>{ord.order_id}</strong>
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{dateStr}</div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, color: '#fff' }}>{ord.customer_name || ord.user_id}</div>
                        <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{ord.shipping_address || 'Default Address'}</div>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.78rem', color: '#cbd5e1' }}>
                          {(ord.items || []).length} items
                        </span>
                      </td>
                      <td style={{ fontFamily: 'monospace', fontWeight: 700, color: '#34d399' }}>
                        ₹{Number(ord.total || 0).toFixed(2)}
                      </td>
                      <td>
                        <span style={{ fontFamily: 'monospace', fontSize: '0.75rem', color: '#06b6d4' }}>
                          {ord.tracking_number || 'TRK-PENDING'}
                        </span>
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
                        {!isDelivered && !isRefunded && (
                          <div style={{ display: 'flex', gap: '0.4rem' }}>
                            <button 
                              className="action-btn"
                              style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
                              onClick={() => handleUpdateStatus(ord.order_id, 'Shipped')}
                              disabled={updatingId === ord.order_id}
                            >
                              Mark Shipped
                            </button>
                            <button 
                              className="action-btn"
                              style={{ padding: '0.2rem 0.5rem', fontSize: '0.72rem' }}
                              onClick={() => handleUpdateStatus(ord.order_id, 'Delivered')}
                              disabled={updatingId === ord.order_id}
                            >
                              Deliver
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
