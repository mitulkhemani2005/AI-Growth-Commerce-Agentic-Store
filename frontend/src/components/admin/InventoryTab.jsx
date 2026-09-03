import React, { useState } from 'react';
import { Package, PlusCircle, Percent, Check, Edit2 } from 'lucide-react';
import { useStore } from '../../context/StoreContext';
import { useAdmin } from '../../context/AdminContext';
import { api } from '../../api/client';

export default function InventoryTab() {
  const { catalog, refreshCatalog, showToast } = useStore();
  const { setIsAddProductModalOpen, setIsBulkPriceModalOpen } = useAdmin();

  const [editingId, setEditingId] = useState(null);
  const [editStock, setEditStock] = useState('');
  const [editPrice, setEditPrice] = useState('');
  const [editBasePrice, setEditBasePrice] = useState('');

  const startEdit = (p) => {
    setEditingId(p.id);
    setEditStock(p.STOCK_REMAINING);
    setEditPrice(p.PRICE);
    setEditBasePrice(p.BASE_PRICE || p.PRICE);
  };

  const saveEdit = async (p) => {
    try {
      await api.adminUpdateInventory({
        product_id: p.id,
        stock: parseInt(editStock),
        price: parseFloat(editPrice),
        base_price: parseFloat(editBasePrice)
      });
      showToast(`Updated ${p.PRODUCT_NAME}!`, 'success');
      setEditingId(null);
      await refreshCatalog();
    } catch (e) {
      showToast(`Update error: ${e.message}`, 'error');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            Inventory & Dual-Pricing Studio (INR ₹, 0% Tax)
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            <strong>Two-Tier Pricing Engine:</strong> 1) <strong>Base Price 🔒</strong> is set strictly by Store Owner as an immutable floor. 2) <strong>Selling Price 📈</strong> is autonomously optimized by AI without breaching the floor.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button 
            className="action-btn"
            onClick={() => setIsBulkPriceModalOpen(true)}
          >
            <Percent size={15} />
            <span>Bulk % Adjust Prices</span>
          </button>
          <button 
            className="action-btn primary"
            onClick={() => setIsAddProductModalOpen(true)}
          >
            <PlusCircle size={15} />
            <span>Add New Product</span>
          </button>
        </div>
      </div>

      <div className="glass-panel">
        <div className="admin-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Product & SKU</th>
                <th>Category</th>
                <th>Stock Units</th>
                <th>Base Price Floor (🔒 Owner Set)</th>
                <th>Selling Price (📈 Dynamic AI)</th>
                <th>Gross Margin</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {catalog.map((p) => {
                const isEditing = editingId === p.id;
                const baseP = parseFloat(p.BASE_PRICE || p.PRICE || 0);
                const sellP = parseFloat(p.PRICE || baseP);
                const margin = sellP - baseP;

                return (
                  <tr key={p.id}>
                    <td>
                      <strong style={{ color: '#fff' }}>{p.PRODUCT_NAME}</strong>
                      <div style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'monospace' }}>{p.id}</div>
                    </td>
                    <td>
                      <span className="prod-badge-cat" style={{ position: 'static' }}>{p.PRODUCT_TYPE}</span>
                    </td>
                    <td>
                      {isEditing ? (
                        <input 
                          type="number"
                          className="form-input"
                          style={{ width: '80px', padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}
                          value={editStock}
                          onChange={(e) => setEditStock(e.target.value)}
                        />
                      ) : (
                        <strong style={{ color: (p.STOCK_REMAINING || 0) <= 0 ? '#fb7185' : '#34d399' }}>
                          {p.STOCK_REMAINING ?? 0}
                        </strong>
                      )}
                    </td>
                    <td>
                      {isEditing ? (
                        <input 
                          type="number"
                          step="0.01"
                          className="form-input"
                          style={{ width: '90px', padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}
                          value={editBasePrice}
                          onChange={(e) => setEditBasePrice(e.target.value)}
                        />
                      ) : (
                        <span style={{ fontFamily: 'monospace', color: '#cbd5e1' }}>
                          ₹{baseP.toFixed(2)}
                        </span>
                      )}
                    </td>
                    <td>
                      {isEditing ? (
                        <input 
                          type="number"
                          step="0.01"
                          className="form-input"
                          style={{ width: '90px', padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}
                          value={editPrice}
                          onChange={(e) => setEditPrice(e.target.value)}
                        />
                      ) : (
                        <span style={{ fontFamily: 'monospace', fontWeight: 800, color: '#22d3ee' }}>
                          ₹{sellP.toFixed(2)}
                        </span>
                      )}
                    </td>
                    <td>
                      <span style={{
                        fontFamily: 'monospace',
                        color: margin > 0 ? '#34d399' : '#94a3b8',
                        fontWeight: 700
                      }}>
                        +{((margin / (baseP || 1)) * 100).toFixed(1)}% (+₹{margin.toFixed(2)})
                      </span>
                    </td>
                    <td>
                      {isEditing ? (
                        <button 
                          className="action-btn primary"
                          style={{ padding: '0.25rem 0.6rem', fontSize: '0.72rem' }}
                          onClick={() => saveEdit(p)}
                        >
                          <Check size={12} />
                          <span>Save</span>
                        </button>
                      ) : (
                        <button 
                          className="action-btn"
                          style={{ padding: '0.25rem 0.6rem', fontSize: '0.72rem' }}
                          onClick={() => startEdit(p)}
                        >
                          <Edit2 size={12} />
                          <span>Edit</span>
                        </button>
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
