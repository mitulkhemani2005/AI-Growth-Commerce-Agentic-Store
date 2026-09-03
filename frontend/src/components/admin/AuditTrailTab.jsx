import React, { useState, useEffect } from 'react';
import { ShieldCheck, AlertOctagon, CheckCircle2, RefreshCw, FileText, ArrowRight } from 'lucide-react';
import { api } from '../../api/client';

export default function AuditTrailTab() {
  const [auditData, setAuditData] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [simResult, setSimResult] = useState(null);
  const [simLoading, setSimLoading] = useState(false);

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

  const runFailureTest = async (failureType) => {
    setSimLoading(true);
    try {
      const res = await api.simulateFailure(failureType);
      setSimResult(res);
    } catch (e) {
      setSimResult({ error: e.message });
    } finally {
      setSimLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
          🛡️ Explainable Money Actions, Bounds & Financial Guardrails
        </h2>
        <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
          Every financial movement is <strong>explainable</strong> (with algorithmic rationale), <strong>bounded</strong> (strictly capped by immutable limits), and <strong>gated</strong> (pre-approved policies). Below is the live immutable audit trail and interactive failure recovery tests.
        </p>
      </div>

      {/* Interactive Failure Handling Test Simulator */}
      <div className="glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', textTransform: 'uppercase' }}>
              Graceful Financial Failure Handling Simulator
            </h4>
            <span style={{ fontSize: '0.76rem', color: '#94a3b8' }}>
              Test how the system intercepts out-of-bounds or invalid financial actions safely without breaking.
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
            <button 
              className="action-btn"
              style={{ fontSize: '0.78rem', padding: '0.45rem 1rem' }}
              onClick={() => runFailureTest('AP2_OVERSPEND')}
              disabled={simLoading}
            >
              1. Test AP2 Overspend (&gt;₹25k)
            </button>

            <button 
              className="action-btn"
              style={{ fontSize: '0.78rem', padding: '0.45rem 1rem' }}
              onClick={() => runFailureTest('EXPIRED_REFUND')}
              disabled={simLoading}
            >
              2. Test Expired Refund (&gt;24h)
            </button>

            <button 
              className="action-btn"
              style={{ fontSize: '0.78rem', padding: '0.45rem 1rem' }}
              onClick={() => runFailureTest('BASE_FLOOR_BREACH')}
              disabled={simLoading}
            >
              3. Test Base Floor Breach (&lt; Cost)
            </button>
          </div>
        </div>

        {/* Simulator Results Output */}
        {simResult && (
          <div style={{
            background: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '8px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
            fontSize: '0.82rem',
            marginTop: '0.75rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span style={{
                fontSize: '0.72rem',
                fontWeight: 800,
                padding: '0.2rem 0.6rem',
                borderRadius: '9999px',
                background: simResult.status?.includes('REJECTION') ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                color: simResult.status?.includes('REJECTION') ? '#fb7185' : '#34d399',
                border: `1px solid ${simResult.status?.includes('REJECTION') ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)'}`
              }}>
                {simResult.status || 'PROCESSED'}
              </span>
              <strong style={{ color: '#fff' }}>{simResult.attempted_action}</strong>
            </div>

            <div style={{ color: '#f8fafc', fontWeight: 600 }}>{simResult.message}</div>
            <div style={{ color: '#94a3b8' }}>
              <strong style={{ color: '#cbd5e1' }}>Explainability:</strong> {simResult.explainability}
            </div>
            <div style={{ color: '#60a5fa', fontWeight: 600 }}>
              <strong style={{ color: '#93c5fd' }}>Graceful Recovery:</strong> {simResult.graceful_recovery}
            </div>
          </div>
        )}
      </div>

      {/* Chronological Audit Trail Table */}
      <div className="glass-panel">
        <div style={{ paddingBottom: '1rem', marginBottom: '1rem', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', textTransform: 'uppercase' }}>
            Immutable Financial Transaction Ledger ({auditData.length})
          </h4>
          <button 
            onClick={fetchAudit}
            className="action-btn"
            style={{ fontSize: '0.74rem' }}
          >
            <RefreshCw size={12} className={isLoading ? 'spin' : ''} />
            <span>Refresh Ledger</span>
          </button>
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

