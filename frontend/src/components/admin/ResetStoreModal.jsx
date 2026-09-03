import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import Modal from '../shared/Modal';

export default function ResetStoreModal() {
  const { isResetConfirmModalOpen, setIsResetConfirmModalOpen, loadAllAdminData } = useAdmin();
  const { refreshCatalog, refreshCart, refreshOrders, showToast } = useStore();
  const [isResetting, setIsResetting] = useState(false);

  const handleConfirmReset = async () => {
    setIsResetting(true);
    try {
      const res = await api.resetStoreComplete();
      if (res.success) {
        showToast('Store successfully reset to initial clean 0-Stock state!', 'success');
        await Promise.all([
          loadAllAdminData(),
          refreshCatalog(),
          refreshCart(),
          refreshOrders()
        ]);
        setIsResetConfirmModalOpen(false);
      } else {
        showToast(res.error || 'Reset failed', 'error');
      }
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <Modal
      isOpen={isResetConfirmModalOpen}
      onClose={() => setIsResetConfirmModalOpen(false)}
      title="Reset Store to 0-Stock State?"
      icon={AlertTriangle}
      maxWidth="480px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', color: '#cbd5e1', fontSize: '0.86rem' }}>
        <p>This action will reset the store to initial clean conditions:</p>
        <ul style={{ marginLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.35rem', color: '#94a3b8' }}>
          <li>Set all catalog products to <strong>0 STOCK</strong> (Wholesale restock required).</li>
          <li>Reset Treasury Bank Balance to <strong>₹10,000.00</strong>.</li>
          <li>Clear all Orders, Reviews, and active Shopping Carts.</li>
          <li>Reset Specialist Agent Salaries to base <strong>₹50 / 100 cycles</strong>.</li>
          <li>Reset 5 AI buyers with staggered purchase schedules.</li>
        </ul>

        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
          <button 
            className="action-btn"
            onClick={() => setIsResetConfirmModalOpen(false)}
            disabled={isResetting}
          >
            Cancel
          </button>
          <button 
            className="action-btn"
            style={{ background: '#f43f5e', borderColor: '#f43f5e', color: '#fff' }}
            onClick={handleConfirmReset}
            disabled={isResetting}
          >
            <span>{isResetting ? 'Resetting Store...' : 'Confirm Reset to 0 Stock'}</span>
          </button>
        </div>
      </div>
    </Modal>
  );
}
