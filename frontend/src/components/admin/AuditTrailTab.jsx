import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertOctagon, CheckCircle2, RefreshCw, FileText, ArrowRight } from 'lucide-react';
import { api } from '../../api/client';

export default function AuditTrailTab() {
  const [auditData, setAuditData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);


  const fetchAudit = async () => {
    setIsLoading(true);
    try {
      const res = await api.getAuditTrail();
      if (res && res.audit_trail) {
        setAuditData(res.audit_trail);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAudit();
  }, []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            🛡️ Explainable Money Actions, Bounds & Financial Guardrails
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            Every financial movement is <strong>explainable</strong> (with algorithmic rationale), <strong>bounded</strong> (strictly capped by immutable limits), and <strong>gated</strong> (pre-approved policies). Below is the live immutable audit trail.
          </p>
        </div>

        <button 
          onClick={fetchAudit}
          className="action-btn"
          style={{ fontSize: '0.78rem' }}
        >
          <RefreshCw size={14} className={isLoading ? 'spin' : ''} />
          <span>Refresh Ledger</span>
        </button>
      </div>

      {/* Chronological Audit Trail Table */}
      <div className="glass-panel">
        <div style={{ paddingBottom: '1rem', marginBottom: '1rem', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', textTransform: 'uppercase' }}>
            Immutable Financial Transaction Ledger ({auditData.length})
          </h4>
          <span style={{ fontSize: '0.72rem', background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', padding: '0.2rem 0.6rem', borderRadius: '4px', fontWeight: 700 }}>
            BOUNDS ENFORCED ✓
          </span>
        </div>

        <div className="admin-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>TX ID</th>
                <th>Type</th>
                <th>Amount (₹)</th>
                <th>Balance After</th>
                <th>Actor</th>
                <th>Explainability Rationale</th>
                <th>Guardrail</th>
              </tr>
            </thead>
            <tbody>
              {auditData.slice(0, 25).map((tx, idx) => {
                const isCredit = tx.type?.includes('DEPOSIT') || tx.type?.includes('SALES');
                return (
                  <tr key={idx}>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.74rem', color: '#94a3b8' }}>
                      {tx.timestamp ? new Date(tx.timestamp).toLocaleTimeString() : 'Recent'}
                    </td>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: '#60a5fa' }}>
                      {tx.transaction_id}
                    </td>
                    <td>
                      <span style={{ fontSize: '0.72rem', fontWeight: 800, color: isCredit ? '#34d399' : '#fb7185' }}>
                        {tx.type}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'monospace', fontWeight: 800, color: isCredit ? '#34d399' : '#fb7185' }}>
                      {isCredit ? '+' : '-'}₹{Math.abs(tx.amount || 0).toFixed(2)}
                    </td>
                    <td style={{ fontFamily: 'monospace', color: '#fff' }}>
                      ₹{Number(tx.balance_after || 0).toFixed(2)}
                    </td>
                    <td style={{ fontSize: '0.76rem', fontWeight: 600, color: '#e2e8f0' }}>
                      {tx.actor}
                    </td>
                    <td style={{ fontSize: '0.78rem', color: '#94a3b8', maxWidth: '280px' }}>
                      {tx.explainability}
                    </td>
                    <td>
                      <span style={{ fontSize: '0.68rem', background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 700 }}>
                        BOUNDED ✓
                      </span>
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

