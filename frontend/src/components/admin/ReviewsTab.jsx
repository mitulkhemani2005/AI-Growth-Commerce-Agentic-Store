import React, { useState } from 'react';
import { Star, Sparkles, RefreshCw, MessageSquare } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';

export default function ReviewsTab() {
  const { adminReviews, loadAllAdminData } = useAdmin();
  const { catalog, refreshCatalog, showToast } = useStore();

  const [generatingId, setGeneratingId] = useState(null);

  const handleGenerateSummary = async (productId) => {
    setGeneratingId(productId);
    try {
      const res = await api.adminGenerateReviewSummary(productId);
      if (res.success) {
        showToast('AI Review Summary successfully synthesized by Ollama!', 'success');
        await Promise.all([refreshCatalog(), loadAllAdminData()]);
      } else {
        showToast(res.error || 'Failed to generate summary', 'error');
      }
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setGeneratingId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      <div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
          AI Review & Feedback Synthesis
        </h2>
        <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
          Customer reviews with automated Ollama LLM sentiment analysis, pro/con extraction, and live catalog summary synchronization.
        </p>
      </div>

      <div className="dashboard-2col">
        {/* AI Generated Product Summaries */}
        <div className="glass-panel">
          <div className="panel-header-bar">
            <h4>
              <Sparkles size={18} style={{ color: '#06b6d4' }} />
              <span>AI Generated Product Summaries</span>
            </h4>
          </div>

          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.85rem', maxHeight: '550px', overflowY: 'auto' }}>
            {catalog.map((prod) => (
              <div 
                key={prod.id}
                style={{
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: '8px',
                  padding: '0.85rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.4rem'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ color: '#fff', fontSize: '0.9rem' }}>{prod.PRODUCT_NAME}</strong>
                  <button 
                    className="action-btn"
                    style={{ padding: '0.25rem 0.55rem', fontSize: '0.72rem' }}
                    onClick={() => handleGenerateSummary(prod.id)}
                    disabled={generatingId === prod.id}
                  >
                    <RefreshCw size={11} className={generatingId === prod.id ? 'spin' : ''} />
                    <span>{generatingId === prod.id ? 'Synthesizing...' : 'Regenerate'}</span>
                  </button>
                </div>

                <p style={{ fontSize: '0.78rem', color: '#94a3b8', fontStyle: 'italic', lineHeight: 1.4 }}>
                  "{prod.AI_SUMMARY || prod.DESCRIPTION || 'No AI summary generated yet.'}"
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Verified Customer Reviews */}
        <div className="glass-panel">
          <div className="panel-header-bar">
            <h4>
              <MessageSquare size={18} style={{ color: '#f59e0b' }} />
              <span>Verified Customer Reviews ({adminReviews.length})</span>
            </h4>
          </div>

          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.85rem', maxHeight: '550px', overflowY: 'auto' }}>
            {adminReviews.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                No customer reviews recorded yet.
              </div>
            ) : (
              adminReviews.map((rev, idx) => (
                <div 
                  key={idx}
                  style={{
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                    borderRadius: '8px',
                    padding: '0.85rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.35rem'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <strong style={{ color: '#fff', fontSize: '0.85rem' }}>{rev.customer_name || 'Customer'}</strong>
                      <span style={{ fontSize: '0.7rem', color: '#06b6d4' }}>({rev.product_name || rev.product_id})</span>
                    </div>

                    <div style={{ color: '#f59e0b', display: 'flex', gap: '2px', fontSize: '0.75rem' }}>
                      {'★'.repeat(rev.rating || 5)}{'☆'.repeat(5 - (rev.rating || 5))}
                    </div>
                  </div>

                  <p style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>{rev.review_text || rev.comment}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
