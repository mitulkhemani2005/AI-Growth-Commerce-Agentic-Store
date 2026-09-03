import React, { useState, useEffect } from 'react';
import { CreditCard, KeyRound, CheckCircle2 } from 'lucide-react';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import Modal from '../shared/Modal';

export default function RazorpayConfigModal() {
  const { isRzpModalOpen, setIsRzpModalOpen, razorpayKey, refreshPaymentConfig, showToast } = useStore();
  const [keyId, setKeyId] = useState('');
  const [keySecret, setKeySecret] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (razorpayKey) setKeyId(razorpayKey);
  }, [razorpayKey]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!keyId.trim() || !keySecret.trim()) {
      showToast('Please enter both Key ID and Key Secret.', 'error');
      return;
    }
    setIsSaving(true);
    try {
      const res = await api.updateRazorpayCredentials(keyId.trim(), keySecret.trim());
      if (res.success) {
        showToast('Razorpay credentials updated successfully!', 'success');
        refreshPaymentConfig();
        setIsRzpModalOpen(false);
      } else {
        showToast(res.error || 'Failed to update credentials', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isRzpModalOpen}
      onClose={() => setIsRzpModalOpen(false)}
      title="Razorpay Gateway Credentials"
      icon={CreditCard}
      maxWidth="480px"
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{
          background: 'rgba(6, 182, 212, 0.1)',
          border: '1px solid rgba(6, 182, 212, 0.25)',
          padding: '0.75rem 1rem',
          borderRadius: '8px',
          fontSize: '0.8rem',
          color: '#cbd5e1'
        }}>
          <strong>⚡ Sandbox & Live Ready:</strong>
          <p style={{ marginTop: '4px', color: '#94a3b8' }}>
            Storefront uses Razorpay test credentials by default. You can input your custom Razorpay Key ID and Secret below.
          </p>
        </div>

        <div className="form-group">
          <label>Razorpay Key ID (e.g. <code>rzp_test_...</code>)</label>
          <input 
            type="text"
            className="form-input"
            value={keyId}
            onChange={(e) => setKeyId(e.target.value)}
            placeholder="rzp_test_..."
            required
          />
        </div>

        <div className="form-group">
          <label>Razorpay Key Secret</label>
          <input 
            type="password"
            className="form-input"
            value={keySecret}
            onChange={(e) => setKeySecret(e.target.value)}
            placeholder="Enter Key Secret"
            required
          />
        </div>

        <button 
          type="submit" 
          className="checkout-btn" 
          disabled={isSaving}
          style={{ marginTop: '0.5rem' }}
        >
          <KeyRound size={16} />
          <span>{isSaving ? 'Saving Credentials...' : 'Save Razorpay Credentials'}</span>
        </button>
      </form>
    </Modal>
  );
}
