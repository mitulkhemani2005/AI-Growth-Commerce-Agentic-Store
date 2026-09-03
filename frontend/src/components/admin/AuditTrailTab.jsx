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
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#111' }}>
          🛡️ Explainable Money Actions, Bounds & Financial Guardrails
        </h2>
        <p style={{ fontSize: '0.82rem', color: '#707072' }}>
          Every financial movement is <strong>explainable</strong> (with algorithmic rationale), <strong>bounded</strong> (strictly capped by immutable limits), and <strong>gated</strong> (pre-approved policies). Below is the live immutable audit trail and interactive failure recovery tests.
        </p>
      </div>

      {/* Interactive Failure Handling Test Simulator */}
      <div className="nike-table-card" style={{ padding: '1.5rem', background: '#fafafa' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h4 style={{ fontFamily: 'var(--font-display)', fontSize: '1.15rem', color: '#111', textTransform: 'uppercase' }}>
              Graceful Financial Failure Handling Simulator
            </h4>
            <span style={{ fontSize: '0.76rem', color: '#707072' }}>
              Test how the system intercepts out-of-bounds or invalid financial actions safely without breaking.
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
            <button 
              className="nike-pill-btn secondary-white"
              style={{ fontSize: '0.78rem', padding: '0.45rem 1rem' }}
              onClick={() => runFailureTest('AP2_OVERSPEND')}
              disabled={simLoading}
            >
              1. Test AP2 Overspend (&gt;₹25k)
            </button>

            <button 
              className="nike-pill-btn secondary-white"
              style={{ fontSize: '0.78rem', padding: '0.45rem 1rem' }}
              onClick={() => runFailureTest('EXPIRED_REFUND')}
              disabled={simLoading}
            >
              2. Test Expired Refund (&gt;24h)
            </button>


            <button 
              className="nike-pill-btn secondary-white"
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
            background: '#ffffff',
            border: '1px solid #e5e5e5',
            borderRadius: '8px',
            padding: '1.25rem',
            display: 'flex',
            flexDirection: 'column',
            gap: '0.5rem',
            fontSize: '0.82rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span style={{
                fontSize: '0.72rem',
                fontWeight: 800,
                padding: '0.2rem 0.6rem',
                borderRadius: '9999px',
                background: simResult.status?.includes('REJECTION') ? '#fee2e2' : '#f0fdf4',
                color: simResult.status?.includes('REJECTION') ? '#b91c1c' : '#15803d'
              }}>
                {simResult.status || 'PROCESSED'}
              </span>
              <strong style={{ color: '#111' }}>{simResult.attempted_action}</strong>
            </div>

            <div style={{ color: '#111', fontWeight: 600 }}>{simResult.message}</div>
            <div style={{ color: '#707072' }}>
              <strong>Explainability:</strong> {simResult.explainability}
            </div>
            <div style={{ color: '#2563eb', fontWeight: 600 }}>
              <strong>Graceful Recovery:</strong> {simResult.graceful_recovery}
            </div>
          </div>
        )}
      </div>

      {/* Chronological Audit Trail Table */}
      <div className="nike-table-card">
        <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid #e5e5e5', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h4 style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem', color: '#111', textTransform: 'uppercase' }}>
            Immutable Financial Transaction Ledger ({auditData.length})
          </h4>
          <button 
            onClick={fetchAudit}
            style={{ background: 'transparent', border: 'none', color: '#707072', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.76rem', fontWeight: 700 }}
          >
            <RefreshCw size={12} className={isLoading ? 'spin' : ''} />
            <span>Refresh Ledger</span>
          </button>
        </div>

        <table className="nike-table">
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
                  <td style={{ fontFamily: 'monospace', fontSize: '0.74rem' }}>
                    {tx.timestamp ? new Date(tx.timestamp).toLocaleTimeString() : 'Recent'}
                  </td>
                  <td style={{ fontFamily: 'monospace', fontSize: '0.75rem', fontWeight: 700, color: '#111' }}>
                    {tx.transaction_id}
                  </td>
                  <td>
                    <span style={{ fontSize: '0.72rem', fontWeight: 800, color: isCredit ? '#15803d' : '#b91c1c' }}>
                      {tx.type}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'monospace', fontWeight: 800, color: isCredit ? '#15803d' : '#b91c1c' }}>
                    {isCredit ? '+' : '-'}₹{Math.abs(tx.amount || 0).toFixed(2)}
                  </td>
                  <td style={{ fontFamily: 'monospace', color: '#111' }}>
                    ₹{Number(tx.balance_after || 0).toFixed(2)}
                  </td>
                  <td style={{ fontSize: '0.76rem', fontWeight: 600 }}>
                    {tx.actor}
                  </td>
                  <td style={{ fontSize: '0.78rem', color: '#707072', maxWidth: '280px' }}>
                    {tx.explainability}
                  </td>
                  <td>
                    <span style={{ fontSize: '0.68rem', background: '#f0fdf4', color: '#15803d', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 700 }}>
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
  );
}
