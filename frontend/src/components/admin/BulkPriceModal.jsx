import React, { useState } from 'react';
import { Percent } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import Modal from '../shared/Modal';

export default function BulkPriceModal() {
  const { isBulkPriceModalOpen, setIsBulkPriceModalOpen, loadAllAdminData } = useAdmin();
  const { refreshCatalog, showToast } = useStore();

  const [category, setCategory] = useState('all');
  const [percentage, setPercentage] = useState(-10);
  const [isApplying, setIsApplying] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsApplying(true);
    try {
      const res = await api.adminBulkPrice(
        category === 'all' ? null : category,
        parseFloat(percentage)
      );

      if (res.success) {
        showToast(res.message || 'Bulk prices adjusted successfully!', 'success');
        await Promise.all([refreshCatalog(), loadAllAdminData()]);
        setIsBulkPriceModalOpen(false);
      } else {
        showToast(res.error || 'Bulk adjustment failed', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <Modal
      isOpen={isBulkPriceModalOpen}
      onClose={() => setIsBulkPriceModalOpen(false)}
      title="Bulk Price Adjustment"
      icon={Percent}
      maxWidth="480px"
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div className="form-group">
          <label>Target Category</label>
          <select 
            className="form-select"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            <option value="all">All Catalog Categories</option>
            <option value="Mobiles">Mobiles</option>
            <option value="Laptops">Laptops</option>
            <option value="Audio">Audio</option>
            <option value="Accessories">Accessories</option>
          </select>
        </div>

        <div className="form-group">
          <label>Percentage Change (+ for Increase, - for Discount)</label>
          <input 
            type="number"
            step="0.5"
            className="form-input"
            value={percentage}
            onChange={(e) => setPercentage(e.target.value)}
            required
            placeholder="e.g. -10 for 10% discount, 5 for 5% raise"
          />
        </div>

        <p style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
          *Note: Selling prices will automatically enforce the <strong>BASE_PRICE floor</strong> — prices will never drop below wholesale base cost.
        </p>

        <button 
          type="submit" 
          className="checkout-btn"
          disabled={isApplying}
        >
          <span>{isApplying ? 'Applying Adjustments...' : 'Apply Price Adjustments'}</span>
        </button>
      </form>
    </Modal>
  );
}
