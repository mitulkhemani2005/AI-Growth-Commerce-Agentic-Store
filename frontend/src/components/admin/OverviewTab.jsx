import React from 'react';
import { 
  Landmark, 
  IndianRupee, 
  TrendingUp, 
  ShoppingBag, 
  PackageCheck, 
  AlertTriangle, 
  Bot, 
  Radio, 
  Terminal, 
  ArrowRight,
  Play 
} from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';

export default function OverviewTab() {
  const { 
    overview, 
    agentsStatus, 
    treasury, 
    agentLogs, 
    agentMessages, 
    setActiveTab, 
    triggerAgent 
  } = useAdmin();

  const kpis = overview?.kpis || {};
  const bankBalance = treasury?.bank_balance ?? 500000;
  const salesRevenue = treasury?.total_sales_revenue ?? kpis.total_revenue ?? 0;
  const stockSpend = treasury?.total_inventory_spend ?? 0;
  const netProfit = salesRevenue - stockSpend;
  const profitMargin = salesRevenue > 0 ? ((netProfit / salesRevenue) * 100).toFixed(1) : '0.0';

  const agentsList = [
    { key: 'price_manager', name: 'Price Manager', role: 'Dynamic Pricing & Margin Floor', icon: '🏷️' },
    { key: 'inventory_manager', name: 'Inventory Manager', role: 'Warehouse Restock & Velocity', icon: '📦' },
    { key: 'order_manager', name: 'Order Manager', role: 'Lifecycle Progression & 24h Refund', icon: '📋' },
    { key: 'dispatcher', name: 'Dispatcher Agent', role: 'Logistics Carrier Tracking', icon: '🚚' },
    { key: 'finance_manager', name: 'Finance Manager', role: 'Revenue, GMV & Refund Governance', icon: '💰' },
    { key: 'review_manager', name: 'Review Agent', role: 'Sentiment Synthesis & Catalog Summaries', icon: '⭐' },
    { key: 'ceo', name: 'CEO Agent', role: 'Strategic Alignment & Owner Briefings', icon: '👔' }
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* 6 Metric KPI Cards */}
      <div className="kpi-cards-grid">
        <div className="kpi-card cyan">
          <div className="kpi-icon-wrap">
            <Landmark size={22} />
          </div>
          <div className="kpi-details">
            <span className="kpi-lbl">CEO Bank Balance</span>
            <div className="kpi-val">₹{Number(bankBalance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Treasury Capital (.env)</span>
          </div>
        </div>

        <div className="kpi-card emerald">
          <div className="kpi-icon-wrap">
            <IndianRupee size={22} />
          </div>
          <div className="kpi-details">
            <span className="kpi-lbl">Total Sales Revenue</span>
            <div className="kpi-val">₹{Number(salesRevenue).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Online orders (0% Tax)</span>
          </div>
        </div>

        <div className="kpi-card purple">
          <div className="kpi-icon-wrap">
            <TrendingUp size={22} />
          </div>
          <div className="kpi-details">
            <span className="kpi-lbl">Net Realized Profit</span>
            <div className="kpi-val">₹{Number(netProfit).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Margin: {profitMargin}%</span>
          </div>
        </div>

        <div className="kpi-card amber">
          <div className="kpi-icon-wrap">
            <ShoppingBag size={22} />
          </div>
          <div className="kpi-details">
            <span className="kpi-lbl">Wholesale Stock Spend</span>
            <div className="kpi-val">₹{Number(stockSpend).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</div>
            <span className="kpi-sub">Acquired at Base Price</span>
          </div>
        </div>

        <div className="kpi-card blue">
          <div className="kpi-icon-wrap">
            <PackageCheck size={22} />
          </div>
          <div className="kpi-details">
            <span className="kpi-lbl">Total Orders</span>
            <div className="kpi-val">{kpis.total_orders || 0}</div>
            <span className="kpi-sub">{kpis.active_orders || 0} active pipeline</span>
          </div>
        </div>

        <div className="kpi-card rose">
          <div className="kpi-icon-wrap">
            <AlertTriangle size={22} />
          </div>
          <div className="kpi-details">
            <span className="kpi-lbl">0-Stock / Low Stock</span>
            <div className="kpi-val">{kpis.low_stock_count ?? 27}</div>
            <span className="kpi-sub">Awaiting Restock</span>
          </div>
        </div>
      </div>

      {/* 2-Column: 7 Agents Grid & Live Message Bus */}
      <div className="dashboard-2col">
        {/* Agents Quick List */}
        <div className="glass-panel">
          <div className="panel-header-bar">
            <h4>
              <Bot size={18} style={{ color: '#06b6d4' }} />
              <span>Autonomous Agent Fleet (7 Agents)</span>
            </h4>
            <button className="action-btn" onClick={() => setActiveTab('agents')}>
              <span>View Hub</span>
              <ArrowRight size={13} />
            </button>
          </div>

          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {agentsList.map((ag) => {
              const liveData = agentsStatus?.agents?.[ag.key] || {};
              const isRunning = liveData.status === 'running' || liveData.enabled !== false;
              return (
                <div 
                  key={ag.key}
                  style={{
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                    borderRadius: '8px',
                    padding: '0.6rem 0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '0.75rem'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                    <span style={{ fontSize: '1.2rem' }}>{ag.icon}</span>
                    <div>
                      <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#fff' }}>{ag.name}</div>
                      <div style={{ fontSize: '0.72rem', color: '#94a3b8' }}>{ag.role}</div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                    <span style={{
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      padding: '0.15rem 0.5rem',
                      borderRadius: '9999px',
                      background: isRunning ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                      color: isRunning ? '#34d399' : '#fb7185'
                    }}>
                      {isRunning ? 'ACTIVE' : 'IDLE'}
                    </span>

                    <button 
                      className="action-btn"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}
                      onClick={() => triggerAgent(ag.key)}
                      title={`Trigger ${ag.name} cycle immediately`}
                    >
                      <Play size={11} />
                      <span>Run</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Live Inter-Agent Message Bus */}
        <div className="glass-panel">
          <div className="panel-header-bar">
            <h4>
              <Radio size={18} style={{ color: '#a855f7' }} />
              <span>⚡ Inter-Agent Real-Time Message Bus</span>
            </h4>
            <span style={{ fontSize: '0.68rem', background: 'rgba(168, 85, 247, 0.2)', color: '#c084fc', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
              COLLABORATING
            </span>
          </div>

          <div className="terminal-feed-box" style={{ height: '340px' }}>
            {agentMessages.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                Connecting to message bus stream...
              </div>
            ) : (
              agentMessages.slice(0, 20).map((msg, idx) => {
                const time = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : 'NOW';
                return (
                  <div key={idx} className="terminal-entry">
                    <span className="term-time">{time}</span>
                    <span className="term-tag purple">{msg.from_agent || 'Agent'} ➔ {msg.to_agent || 'All'}</span>
                    <span style={{ color: '#e2e8f0', wordBreak: 'break-word' }}>
                      <strong>[{msg.subject || 'DIRECTIVE'}]</strong> {typeof msg.content === 'object' ? JSON.stringify(msg.content) : String(msg.content || '')}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* 24/7 Agent Decision & Audit Activity Stream */}
      <div className="glass-panel">
        <div className="panel-header-bar">
          <h4>
            <Terminal size={18} style={{ color: '#10b981' }} />
            <span>📜 24/7 Autonomous Decisions & Warehouse Audit Log</span>
          </h4>
          <span style={{ fontSize: '0.68rem', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
            LIVE STREAM
          </span>
        </div>

        <div className="terminal-feed-box" style={{ maxHeight: '260px' }}>
          {agentLogs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
              Awaiting agent autonomous execution events...
            </div>
          ) : (
            agentLogs.slice(0, 30).map((log, idx) => {
              const time = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : 'NOW';
              return (
                <div key={idx} className="terminal-entry">
                  <span className="term-time">{time}</span>
                  <span className="term-tag emerald">{log.agent_name || 'System'}</span>
                  <span style={{ color: '#94a3b8' }}>
                    <strong style={{ color: '#fff' }}>{log.action || 'EXECUTE'}:</strong> {typeof log.details === 'object' ? JSON.stringify(log.details) : String(log.details || '')}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
