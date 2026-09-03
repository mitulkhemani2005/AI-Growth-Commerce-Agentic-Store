import React, { useState } from 'react';
import { PlusCircle } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import Modal from '../shared/Modal';

export default function AddProductModal() {
  const { isAddProductModalOpen, setIsAddProductModalOpen, loadAllAdminData } = useAdmin();
  const { refreshCatalog, showToast } = useStore();

  const [formData, setFormData] = useState({
    PRODUCT_NAME: '',
    PRODUCT_TYPE: 'Mobiles',
    PRODUCT_SIZE: 'Standard',
    BASE_PRICE: 499,
    PRICE: 599,
    STOCK_REMAINING: 15,
    DESCRIPTION: '',
    IMAGE: '/static/images/phone_flagship.svg'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.PRODUCT_NAME.trim()) return;
    setIsSubmitting(true);

    try {
      const res = await api.adminAddProduct({
        ...formData,
        BASE_PRICE: parseFloat(formData.BASE_PRICE),
        PRICE: parseFloat(formData.PRICE),
        STOCK_REMAINING: parseInt(formData.STOCK_REMAINING)
      });

      if (res.success) {
        showToast(`Product ${formData.PRODUCT_NAME} added successfully!`, 'success');
        await Promise.all([refreshCatalog(), loadAllAdminData()]);
        setIsAddProductModalOpen(false);
      } else {
        showToast(res.error || 'Failed to add product', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      isOpen={isAddProductModalOpen}
      onClose={() => setIsAddProductModalOpen(false)}
      title="Add New Catalog Product"
      icon={PlusCircle}
      maxWidth="560px"
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div className="form-group">
          <label>Product Name</label>
          <input 
            type="text" 
            className="form-input" 
            required 
            placeholder="e.g. Apex HyperFlex Pro"
            value={formData.PRODUCT_NAME}
            onChange={(e) => setFormData({ ...formData, PRODUCT_NAME: e.target.value })}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
          <div className="form-group">
            <label>Category</label>
            <select 
              className="form-select"
              value={formData.PRODUCT_TYPE}
              onChange={(e) => setFormData({ ...formData, PRODUCT_TYPE: e.target.value })}
            >
              <option value="Mobiles">Mobiles</option>
              <option value="Laptops">Laptops</option>
              <option value="Audio">Audio</option>
              <option value="Accessories">Accessories</option>
            </select>
          </div>

          <div className="form-group">
            <label>Specs / Size</label>
            <input 
              type="text" 
              className="form-input"
              value={formData.PRODUCT_SIZE}
              onChange={(e) => setFormData({ ...formData, PRODUCT_SIZE: e.target.value })}
              placeholder="e.g. 16GB/512GB"
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
          <div className="form-group">
            <label>Base Price Floor (₹)</label>
            <input 
              type="number" 
              step="0.01" 
              className="form-input"
              required
              value={formData.BASE_PRICE}
              onChange={(e) => setFormData({ ...formData, BASE_PRICE: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label>Initial Price (₹)</label>
            <input 
              type="number" 
              step="0.01" 
              className="form-input"
              required
              value={formData.PRICE}
              onChange={(e) => setFormData({ ...formData, PRICE: e.target.value })}
            />
          </div>

          <div className="form-group">
            <label>Initial Stock Units</label>
            <input 
              type="number" 
              min="0"
              className="form-input"
              required
              value={formData.STOCK_REMAINING}
              onChange={(e) => setFormData({ ...formData, STOCK_REMAINING: e.target.value })}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Description & Technical Specs</label>
          <textarea 
            rows="3"
            className="form-textarea"
            value={formData.DESCRIPTION}
            onChange={(e) => setFormData({ ...formData, DESCRIPTION: e.target.value })}
            placeholder="Specs, hardware details, battery life, features..."
          />
        </div>

        <button 
          type="submit" 
          className="checkout-btn"
          disabled={isSubmitting}
        >
          <span>{isSubmitting ? 'Adding...' : 'Add Product to Inventory'}</span>
        </button>
      </form>
    </Modal>
  );
}
