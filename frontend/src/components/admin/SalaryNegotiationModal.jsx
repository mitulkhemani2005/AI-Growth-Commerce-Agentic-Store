import React, { useState, useEffect } from 'react';
import { Briefcase, Send, Check, MessageSquare } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
import Modal from '../shared/Modal';

export default function SalaryNegotiationModal() {
  const { isNegotiateModalOpen, setIsNegotiateModalOpen, negotiatingAgent, loadAllAdminData } = useAdmin();
  const { showToast } = useStore();

  const [proposedSalary, setProposedSalary] = useState(75);
  const [rationale, setRationale] = useState('High SLA adherence and proactive store growth');
  const [dialogueThread, setDialogueThread] = useState([]);
  const [isSending, setIsSending] = useState(false);

  useEffect(() => {
    if (negotiatingAgent) {
      setProposedSalary(negotiatingAgent.current_salary || 50);
      setDialogueThread(negotiatingAgent.negotiation_history || [
        { speaker: 'CEO Agent', message: `Initial compensation established at ₹${negotiatingAgent.current_salary || 50} per 100 cycles.` }
      ]);
    }
  }, [negotiatingAgent]);

  const handleSendProposal = async (e) => {
    e.preventDefault();
    if (!negotiatingAgent || isSending) return;
    setIsSending(true);

    try {
      const res = await api.negotiateAgentSalary(
        negotiatingAgent.name,
        parseFloat(proposedSalary),
        rationale
      );

      if (res.success) {
        setDialogueThread(prev => [
          ...prev,
          { speaker: 'Store Owner', message: `Proposed: ₹${proposedSalary} — "${rationale}"` },
          { speaker: negotiatingAgent.name, message: res.counter_offer || res.response || res.message }
        ]);
        showToast('Agent formulated counter-offer!', 'info');
      } else {
        showToast(res.error || 'Negotiation failed', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsSending(false);
    }
  };

  const handleAcceptAgreement = async () => {
    if (!negotiatingAgent) return;
    try {
      await api.updateAgentSalary(negotiatingAgent.name, parseFloat(proposedSalary), 'Agreed');
      showToast(`Agreed to ₹${proposedSalary} / 100 cycles for ${negotiatingAgent.name}!`, 'success');
      await loadAllAdminData();
      setIsNegotiateModalOpen(false);
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  if (!negotiatingAgent) return null;

  return (
    <Modal
      isOpen={isNegotiateModalOpen}
      onClose={() => setIsNegotiateModalOpen(false)}
      title={`Interactive Salary Negotiation: ${negotiatingAgent.name}`}
      icon={Briefcase}
      maxWidth="680px"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{
          background: 'rgba(245, 158, 11, 0.1)',
          border: '1px solid rgba(245, 158, 11, 0.25)',
          borderRadius: '8px',
          padding: '0.75rem 1rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: '0.82rem'
        }}>
          <div>
            <strong style={{ color: '#fff' }}>{negotiatingAgent.role_title}</strong>
            <div style={{ color: '#fbbf24', fontSize: '0.74rem' }}>
              Current Rate: ₹{negotiatingAgent.current_salary || 50} / 100 cycles • Performance: {negotiatingAgent.performance_score || 95}%
            </div>
          </div>
          <span style={{ fontSize: '0.72rem', background: 'rgba(245, 158, 11, 0.2)', color: '#fbbf24', padding: '0.2rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
            {negotiatingAgent.negotiation_status || 'Agreed'}
          </span>
        </div>

        {/* Negotiation Chat Thread */}
        <div style={{
          background: '#050811',
          border: '1px solid rgba(255, 255, 255, 0.08)',
          borderRadius: '8px',
          padding: '1rem',
          maxHeight: '260px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.65rem',
          fontSize: '0.82rem'
        }}>
          {dialogueThread.map((turn, idx) => {
            const isOwner = turn.speaker?.includes('Owner');
            return (
              <div key={idx} style={{
                background: isOwner ? 'rgba(6, 182, 212, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                border: `1px solid ${isOwner ? 'rgba(6, 182, 212, 0.25)' : 'rgba(255, 255, 255, 0.06)'}`,
                padding: '0.6rem 0.85rem',
                borderRadius: '6px'
              }}>
                <strong style={{ color: isOwner ? '#22d3ee' : '#c084fc', display: 'block', fontSize: '0.74rem', marginBottom: '2px' }}>
                  {turn.speaker}:
                </strong>
                <span style={{ color: '#cbd5e1' }}>{turn.message}</span>
              </div>
            );
          })}
        </div>

        {/* Proposal Form */}
        <form onSubmit={handleSendProposal} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '0.75rem' }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Proposed Rate (₹ / 100 cycles)</label>
              <input 
                type="number"
                min="10"
                step="5"
                className="form-input"
                value={proposedSalary}
                onChange={(e) => setProposedSalary(e.target.value)}
                required
              />
            </div>

            <div className="form-group" style={{ marginBottom: 0 }}>
              <label>Owner Rationale / Performance Justification</label>
              <input 
                type="text"
                className="form-input"
                value={rationale}
                onChange={(e) => setRationale(e.target.value)}
                placeholder="e.g. High order velocity & store growth"
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
            <button 
              type="submit" 
              className="action-btn primary"
              style={{ flex: 1, justifyContent: 'center' }}
              disabled={isSending}
            >
              <Send size={15} />
              <span>{isSending ? 'Formulating Response...' : 'Send Salary Proposal'}</span>
            </button>

            <button 
              type="button" 
              className="action-btn"
              style={{ background: 'rgba(16, 185, 129, 0.2)', borderColor: '#10b981', color: '#34d399', justifyContent: 'center' }}
              onClick={handleAcceptAgreement}
            >
              <Check size={15} />
              <span>Accept Agreement</span>
            </button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
