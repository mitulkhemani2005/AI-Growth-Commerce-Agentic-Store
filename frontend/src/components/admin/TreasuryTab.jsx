import React, { useState } from 'react';
import { 
  Wallet, 
  PlusCircle, 
  Send, 
  CheckCircle, 
  Users, 
  Receipt, 
  MessagesSquare, 
  Sparkles, 
  Play, 
  TrendingUp, 
  Award, 
  RotateCcw,
  IndianRupee 
} from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';

export default function TreasuryTab() {
  const { 
    treasury, 
    salaries, 
    loadAllAdminData, 
    setNegotiatingAgent, 
    setIsNegotiateModalOpen,
    setIsResetConfirmModalOpen 
  } = useAdmin();
  const { catalog, refreshCatalog, showToast } = useStore();


  // Stock Acquisition Console state
  const [selectedProdId, setSelectedProdId] = useState(catalog[0]?.id || 'prod_cyberflex_runner');
  const [acquireQty, setAcquireQty] = useState(20);
  const [isAcquiring, setIsAcquiring] = useState(false);

  // CEO Meeting state
  const [meetingTopic, setMeetingTopic] = useState('Wholesale inventory restock budget, base price margins, and autonomous buyer demand');
  const [meetingTranscript, setMeetingTranscript] = useState(null);
  const [isConvening, setIsConvening] = useState(false);

  const bankBalance = Number(treasury?.bank_balance ?? 500000);
  const salesRevenue = Number(treasury?.total_sales_revenue ?? 0);
  const stockSpend = Number(treasury?.total_inventory_spend ?? 0);
  const salariesPaid = Number(treasury?.total_salaries_paid ?? 0);
  const refundsProcessed = Number(treasury?.total_refunds_deducted ?? 0);
  const netProfit = salesRevenue - stockSpend - salariesPaid;

  const targetProd = catalog.find(p => p.id === selectedProdId) || catalog[0] || {};
  const basePrice = Number(targetProd.BASE_PRICE || targetProd.PRICE || 100);
  const sellingPrice = Number(targetProd.PRICE || basePrice);
  const unitMargin = sellingPrice - basePrice;
  const totalCost = basePrice * acquireQty;
  const remainingBalance = bankBalance - totalCost;

  // Handle wholesale acquisition
  const handleAcquireStock = async () => {
    if (acquireQty <= 0) return;
    if (totalCost > bankBalance) {
      showToast('Insufficient CEO Treasury Bank Balance!', 'error');
      return;
    }
    setIsAcquiring(true);
    try {
      const res = await api.acquireWholesaleStock(selectedProdId, acquireQty, 'Store Owner');
      if (res.success) {
        showToast(`Acquired ${acquireQty} units of ${targetProd.PRODUCT_NAME}!`, 'success');
        await Promise.all([loadAllAdminData(), refreshCatalog()]);
      } else {
        showToast(res.error || 'Acquisition failed', 'error');
      }
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setIsAcquiring(false);
    }
  };

  // Disburse Full Payroll
  const handleDisbursePayroll = async () => {
    try {
      const res = await api.payAgentSalaries(null, 'Store Owner');
      if (res.success) {
        showToast(`Disbursed full payroll of ₹${res.total_disbursed?.toFixed(2)} to 7 agents!`, 'success');
        await loadAllAdminData();
      } else {
        showToast(res.error || 'Payroll disbursal failed', 'error');
      }
    } catch (e) {
      showToast(e.message, 'error');
    }
  };

  // Convene CEO Meeting
  const handleConveneMeeting = async () => {
    if (!meetingTopic.trim() || isConvening) return;
    setIsConvening(true);
    try {
      const res = await api.startCEODiscussion(meetingTopic.trim(), 'ALL_AGENTS');
      setMeetingTranscript(res);
      showToast('CEO Strategic Roundtable concluded!', 'success');
    } catch (e) {
      showToast(`Meeting error: ${e.message}`, 'error');
    } finally {
      setIsConvening(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Intro & Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            💰 CEO Treasury, Wholesale Stock Acquisition & Agent Salaries
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            Inventory starts at <strong>0 stock</strong> — CEO acquires wholesale inventory at <strong>BASE_PRICE floor</strong> to generate profit when sold to customers and AI buyers.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button 
            className="action-btn danger"
            style={{ background: 'rgba(244, 63, 94, 0.12)', borderColor: 'rgba(244, 63, 94, 0.35)', color: '#fb7185' }}
            onClick={() => setIsResetConfirmModalOpen(true)}
          >
            <RotateCcw size={14} />
            <span>Reset to Base Condition</span>
          </button>

          <button 
            className="action-btn"
            style={{ background: 'linear-gradient(135deg, #10b981, #059669)', color: '#fff', border: 'none' }}
            onClick={handleDisbursePayroll}
          >
            <Send size={15} />
            <span>Disburse Full Payroll</span>
          </button>
        </div>
      </div>


      {/* Treasury Metric Cards */}
      <div className="kpi-cards-grid">
        <div className="kpi-card cyan">
          <div className="kpi-details">
            <span className="kpi-lbl">CEO Bank Balance</span>
            <div className="kpi-val">₹{bankBalance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Liquid Capital</span>
          </div>
        </div>

        <div className="kpi-card emerald">
          <div className="kpi-details">
            <span className="kpi-lbl">Total Sales Revenue</span>
            <div className="kpi-val">₹{salesRevenue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Deposited to Treasury</span>
          </div>
        </div>

        <div className="kpi-card purple">
          <div className="kpi-details">
            <span className="kpi-lbl">Net Realized Profit</span>
            <div className="kpi-val">₹{netProfit.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Net after Spend & Salaries</span>
          </div>
        </div>

        <div className="kpi-card amber">
          <div className="kpi-details">
            <span className="kpi-lbl">Wholesale Stock Spend</span>
            <div className="kpi-val">₹{stockSpend.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Cost at BASE_PRICE</span>
          </div>
        </div>

        <div className="kpi-card blue">
          <div className="kpi-details">
            <span className="kpi-lbl">Agent Salaries Paid</span>
            <div className="kpi-val">₹{salariesPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">7 Agents Disbursed</span>
          </div>
        </div>

        <div className="kpi-card rose">
          <div className="kpi-details">
            <span className="kpi-lbl">Refunds Processed</span>
            <div className="kpi-val">₹{refundsProcessed.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">24h Pre-Shipment Only</span>
          </div>
        </div>
      </div>

      {/* 2-Column: Stock Acquisition Console & Recent Treasury Ledger */}
      <div className="dashboard-2col">
        {/* Wholesale Acquisition Console */}
        <div className="glass-panel">
          <div className="panel-header-bar">
            <h4>
              <PlusCircle size={18} style={{ color: '#06b6d4' }} />
              <span>📦 Wholesale Inventory Stock Acquisition Console</span>
            </h4>
            <span style={{ fontSize: '0.68rem', background: 'rgba(6, 182, 212, 0.2)', color: '#22d3ee', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
              BASE_PRICE Floor
            </span>
          </div>

          <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <p style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              Acquire inventory at the wholesale <code>BASE_PRICE</code>. When sold at <code>PRICE</code>, the margin <code>(PRICE - BASE_PRICE)</code> is realized as net profit.
            </p>

            <div className="form-group">
              <label>Select Product to Restock</label>
              <select 
                className="form-select"
                value={selectedProdId}
                onChange={(e) => setSelectedProdId(e.target.value)}
              >
                {catalog.map(p => (
                  <option key={p.id} value={p.id}>
                    {p.PRODUCT_NAME} ({p.PRODUCT_TYPE}) — Stock: {p.STOCK_REMAINING}
                  </option>
                ))}
              </select>
            </div>

            {/* Price & Margin Preview */}
            <div style={{
              background: 'rgba(8, 12, 21, 0.7)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '8px',
              padding: '0.85rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.4rem',
              fontSize: '0.82rem'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>Current Stock:</span>
                <strong style={{ color: (targetProd.STOCK_REMAINING || 0) <= 0 ? '#fb7185' : '#34d399' }}>
                  {targetProd.STOCK_REMAINING || 0} Units {(targetProd.STOCK_REMAINING || 0) <= 0 ? '(OUT OF STOCK)' : ''}
                </strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>Wholesale Base Price (Cost):</span>
                <strong style={{ color: '#fff' }}>₹{basePrice.toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>Current Selling Price:</span>
                <strong style={{ color: '#22d3ee' }}>₹{sellingPrice.toFixed(2)}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>Gross Margin Per Unit:</span>
                <strong style={{ color: '#34d399' }}>+₹{unitMargin.toFixed(2)}</strong>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Units to Purchase</label>
                <input 
                  type="number" 
                  min="1" 
                  max="500"
                  className="form-input"
                  value={acquireQty}
                  onChange={(e) => setAcquireQty(Math.max(1, parseInt(e.target.value) || 1))}
                />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Total Acquisition Cost</label>
                <input 
                  type="text" 
                  readOnly 
                  className="form-input" 
                  style={{ background: 'rgba(255, 255, 255, 0.04)', color: '#22d3ee', fontWeight: 800 }}
                  value={`₹${totalCost.toFixed(2)}`}
                />
              </div>
            </div>

            <div style={{ fontSize: '0.76rem', color: '#94a3b8', display: 'flex', justifyContent: 'space-between' }}>
              <span>Bank Balance after purchase:</span>
              <strong style={{ color: remainingBalance >= 0 ? '#34d399' : '#fb7185' }}>
                ₹{remainingBalance.toFixed(2)}
              </strong>
            </div>

            <button 
              className="checkout-btn"
              onClick={handleAcquireStock}
              disabled={isAcquiring || totalCost > bankBalance}
            >
              <CheckCircle size={16} />
              <span>{isAcquiring ? 'Acquiring...' : 'Acquire Stock & Pay from Bank'}</span>
            </button>
          </div>
        </div>

        {/* Live Treasury Cash-Flow Ledger */}
        <div className="glass-panel">
          <div className="panel-header-bar">
            <h4>
              <Receipt size={18} style={{ color: '#10b981' }} />
              <span>📑 Live Treasury Cash-Flow Ledger</span>
            </h4>
            <span style={{ fontSize: '0.68rem', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
              AUDITED
            </span>
          </div>

          <div style={{ padding: '0.5rem', maxHeight: '430px', overflowY: 'auto' }}>
            {(treasury?.transactions || []).length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                No treasury transactions recorded yet.
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Amount (₹)</th>
                    <th>Balance After</th>
                    <th>Actor / Details</th>
                  </tr>
                </thead>
                <tbody>
                  {(treasury?.transactions || []).slice(0, 15).map((tx, idx) => {
                    const isCredit = tx.type?.includes('DEPOSIT') || tx.type?.includes('CAPITAL') || tx.type?.includes('SALES');
                    return (
                      <tr key={idx}>
                        <td>
                          <span style={{
                            fontSize: '0.7rem',
                            fontWeight: 700,
                            color: isCredit ? '#34d399' : '#fb7185'
                          }}>
                            {tx.type}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'monospace', fontWeight: 700, color: isCredit ? '#34d399' : '#fb7185' }}>
                          {isCredit ? '+' : '-'}₹{Math.abs(Number(tx.amount || 0)).toFixed(2)}
                        </td>
                        <td style={{ fontFamily: 'monospace', color: '#cbd5e1' }}>
                          ₹{Number(tx.balance_after || 0).toFixed(2)}
                        </td>
                        <td style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                          {tx.description || tx.actor || 'System'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Specialist Agent Salary Management Table */}
      <div className="glass-panel">
        <div className="panel-header-bar">
          <h4>
            <Award size={18} style={{ color: '#f59e0b' }} />
            <span>💼 Specialist Agent Salary Management & Interactive Negotiation</span>
          </h4>
          <span style={{ fontSize: '0.72rem', background: 'rgba(245, 158, 11, 0.2)', color: '#fbbf24', padding: '0.2rem 0.6rem', borderRadius: '4px', fontWeight: 700 }}>
            Payroll Pool
          </span>
        </div>

        <div className="admin-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Agent Specialist</th>
                <th>Domain Role</th>
                <th>Rate (₹ / 100 Cycles)</th>
                <th>Total Earned (₹)</th>
                <th>Performance</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const salaryItems = Array.isArray(salaries?.salaries) 
                  ? salaries.salaries 
                  : (salaries?.salaries_map ? Object.entries(salaries.salaries_map).map(([k, v]) => ({ agent_name: k, ...v })) : []);

                if (salaryItems.length === 0) {
                  return (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', color: '#64748b', padding: '2rem' }}>
                        Loading agent salary records...
                      </td>
                    </tr>
                  );
                }

                return salaryItems.map((sal, idx) => {
                  const agentName = sal.agent_name || sal.name || `Specialist Agent ${idx + 1}`;
                  const roleTitle = sal.role || sal.role_title || 'Autonomous Specialist';
                  const rate = Number(sal.salary_amount ?? sal.current_salary ?? 50);
                  const totalEarned = Number(sal.total_earned ?? 0);
                  const performance = sal.performance_score ?? 95;
                  const status = sal.negotiation_status || (sal.owner_decided ? 'Owner-Decided' : 'Agreed');

                  return (
                    <tr key={agentName}>
                      <td>
                        <strong style={{ color: '#fff' }}>{agentName}</strong>
                      </td>
                      <td style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                        {roleTitle}
                      </td>
                      <td style={{ fontFamily: 'monospace', fontWeight: 700, color: '#34d399' }}>
                        ₹{rate.toFixed(2)}
                      </td>
                      <td style={{ fontFamily: 'monospace', color: '#cbd5e1' }}>
                        ₹{totalEarned.toFixed(2)}
                      </td>
                      <td>
                        <span style={{
                          background: 'rgba(16, 185, 129, 0.15)',
                          color: '#34d399',
                          padding: '0.15rem 0.45rem',
                          borderRadius: '4px',
                          fontWeight: 700,
                          fontSize: '0.74rem'
                        }}>
                          {performance}%
                        </span>
                      </td>
                      <td>
                        <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
                          {status}
                        </span>
                      </td>
                      <td>
                        <button 
                          className="action-btn"
                          style={{ padding: '0.25rem 0.65rem', fontSize: '0.72rem' }}
                          onClick={() => {
                            setNegotiatingAgent({ name: agentName, role_title: roleTitle, current_salary: rate, ...sal });
                            setIsNegotiateModalOpen(true);
                          }}
                        >
                          Negotiate Salary
                        </button>
                      </td>
                    </tr>
                  );
                });
              })()}
            </tbody>

          </table>
        </div>
      </div>

      {/* CEO Strategic Multi-Agent Roundtable Room */}
      <div className="glass-panel">
        <div className="panel-header-bar">
          <h4>
            <MessagesSquare size={18} style={{ color: '#ec4899' }} />
            <span>👔 CEO Strategic Multi-Agent Roundtable Discussion Room</span>
          </h4>
          <span style={{ fontSize: '0.68rem', background: 'rgba(236, 72, 153, 0.2)', color: '#f472b6', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
            LLM Roundtable
          </span>
        </div>

        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
            <input 
              type="text"
              className="form-input"
              style={{ flex: 2 }}
              value={meetingTopic}
              onChange={(e) => setMeetingTopic(e.target.value)}
              placeholder="Discussion Agenda..."
            />
            <button 
              className="action-btn primary"
              onClick={handleConveneMeeting}
              disabled={isConvening}
            >
              <Play size={14} className={isConvening ? 'spin' : ''} />
              <span>{isConvening ? 'Meeting in Progress...' : 'Convene Meeting'}</span>
            </button>
          </div>

          {/* Transcript Box */}
          <div style={{
            background: '#050811',
            borderRadius: '8px',
            padding: '1.25rem',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            minHeight: '140px',
            maxHeight: '340px',
            overflowY: 'auto',
            fontSize: '0.84rem'
          }}>
            {!meetingTranscript ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                No meeting currently in session. Enter an agenda above and click <strong>Convene Meeting</strong> to gather all specialist agents.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                <h5 style={{ color: '#c084fc', fontSize: '0.9rem', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', paddingBottom: '0.4rem' }}>
                  Agenda: {meetingTranscript.topic || meetingTopic}
                </h5>
                {(meetingTranscript.dialogue || meetingTranscript.turns || []).map((turn, tIdx) => (
                  <div key={tIdx} style={{ display: 'flex', gap: '0.65rem' }}>
                    <strong style={{ color: '#22d3ee', minWidth: '130px', flexShrink: 0 }}>
                      {turn.speaker || turn.agent || 'Agent'}:
                    </strong>
                    <span style={{ color: '#cbd5e1' }}>{turn.text || turn.statement || turn.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
