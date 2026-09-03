import React, { useState } from 'react';
import { 
  Bot, 
  PlayCircle, 
  Clock, 
  Terminal, 
  Sparkles, 
  CheckCircle2,
  Check,
  Zap
} from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';

export default function AgentsTab() {
  const { 
    agentsStatus, 
    agentLogs, 
    triggerAgent, 
    triggerAllAgents, 
    isScanningFleet,
    fetchTelemetry 
  } = useAdmin();
  const { showToast } = useStore();

  const [intervalInputs, setIntervalInputs] = useState({});
  const [savingKey, setSavingKey] = useState(null);

  const agentsMeta = [
    { key: 'price_manager', name: 'Price Manager Agent', role: 'Dynamic Pricing & Margin Floor Enforcement', defaultInterval: 25 },
    { key: 'inventory_manager', name: 'Inventory Manager Agent', role: 'Warehouse Restock & Inventory Velocity', defaultInterval: 20 },
    { key: 'order_manager', name: 'Order Management Agent', role: 'Order Lifecycle Tracking & 24h Refund Rule', defaultInterval: 20 },
    { key: 'dispatcher', name: 'Dispatcher Agent', role: 'Logistics Packaging & Carrier Tracking Numbers', defaultInterval: 15 },
    { key: 'finance_manager', name: 'Finance Manager Agent', role: 'Revenue Auditing, GMV & Refund Governance', defaultInterval: 30 },
    { key: 'review_manager', name: 'Review & Feedback Agent', role: 'Sentiment Synthesis & Catalog Summaries', defaultInterval: 45 },
    { key: 'ceo', name: 'CEO Agent', role: 'Executive Fleet Commander & Owner Strategic Briefings', defaultInterval: 30 }
  ];

  const handleUpdateInterval = async (agentKey, explicitVal = null) => {
    const rawVal = explicitVal !== null ? explicitVal : intervalInputs[agentKey];
    const val = parseInt(rawVal);
    if (!val || val < 5) {
      showToast('Interval must be at least 5 seconds', 'error');
      return;
    }
    setSavingKey(agentKey);
    try {
      await api.updateAgentInterval(agentKey, val);
      await fetchTelemetry();
      showToast(`Updated interval for ${agentKey.replace('_', ' ')} to ${val}s!`, 'success');
    } catch (e) {
      showToast(`Failed to update interval: ${e.message}`, 'error');
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Intro & Full Fleet Scan */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            Autonomous Agent Fleet (7 Collaborative Agents)
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            Configure cycle intervals and execute immediate passes for all 7 specialist agents. Each agent maintains continuous vigilance over store pricing, stock velocity, order progression, and refund governance.
          </p>
        </div>

        <button 
          className="action-btn primary"
          onClick={triggerAllAgents}
          disabled={isScanningFleet}
        >
          <PlayCircle size={16} />
          <span>{isScanningFleet ? 'Scanning Fleet...' : 'Trigger Full Fleet Scan'}</span>
        </button>
      </div>

      {/* 7 Detailed Agent Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem' }}>
        {agentsMeta.map((ag) => {
          const liveData = agentsStatus?.agents?.[ag.key] || {};
          const currentInterval = liveData.interval_seconds || ag.defaultInterval;
          const actionsCount = liveData.actions_count || 0;
          const lastAction = liveData.last_action_time ? new Date(liveData.last_action_time).toLocaleTimeString() : 'Recent';
          const isSaving = savingKey === ag.key;

          return (
            <div key={ag.key} className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                <div>
                  <h4 style={{ color: '#fff', fontSize: '1.05rem', fontWeight: 700 }}>{ag.name}</h4>
                  <span style={{ fontSize: '0.74rem', color: '#06b6d4' }}>{ag.role}</span>
                </div>
                <span style={{ fontSize: '0.68rem', background: 'rgba(16, 185, 129, 0.15)', color: '#34d399', padding: '0.15rem 0.5rem', borderRadius: '4px', fontWeight: 700 }}>
                  24/7 ACTIVE
                </span>
              </div>

              <div style={{
                background: 'rgba(8, 12, 21, 0.6)',
                borderRadius: '8px',
                padding: '0.75rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.35rem',
                fontSize: '0.76rem',
                marginBottom: '1rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Actions Executed:</span>
                  <strong style={{ color: '#fff' }}>{actionsCount} cycles</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Last Execution:</span>
                  <strong style={{ color: '#22d3ee' }}>{lastAction}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Configured Cycle:</span>
                  <strong style={{ color: '#34d399' }}>Every {currentInterval}s</strong>
                </div>
              </div>

              {/* Interval Preset Chips */}
              <div style={{ marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.7rem', color: '#94a3b8', display: 'block', marginBottom: '0.35rem' }}>
                  Quick Interval Presets:
                </span>
                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                  {[15, 30, 60, 120].map((sec) => (
                    <button
                      key={sec}
                      type="button"
                      className="action-btn"
                      style={{
                        padding: '0.15rem 0.45rem',
                        fontSize: '0.7rem',
                        background: currentInterval === sec ? 'rgba(6, 182, 212, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                        borderColor: currentInterval === sec ? 'rgba(6, 182, 212, 0.5)' : 'rgba(255, 255, 255, 0.1)',
                        color: currentInterval === sec ? '#38bdf8' : '#94a3b8'
                      }}
                      onClick={() => handleUpdateInterval(ag.key, sec)}
                    >
                      {sec}s
                    </button>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: 'auto' }}>
                <input 
                  type="number"
                  min="5"
                  max="3600"
                  placeholder={`${currentInterval}s`}
                  className="form-input"
                  style={{ width: '85px', padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
                  value={intervalInputs[ag.key] !== undefined ? intervalInputs[ag.key] : ''}
                  onChange={(e) => setIntervalInputs({ ...intervalInputs, [ag.key]: e.target.value })}
                />
                <button 
                  className="action-btn"
                  style={{ fontSize: '0.75rem', padding: '0.4rem 0.75rem' }}
                  onClick={() => handleUpdateInterval(ag.key)}
                  disabled={isSaving}
                >
                  {isSaving ? 'Saving...' : 'Set Interval'}
                </button>
                <button 
                  className="action-btn primary"
                  style={{ fontSize: '0.75rem', padding: '0.4rem 0.75rem', marginLeft: 'auto' }}
                  onClick={() => triggerAgent(ag.key)}
                >
                  Trigger Now
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Recent Autonomous Agent Decisions Log */}
      <div className="glass-panel">
        <div className="panel-header-bar">
          <h4>
            <Terminal size={18} style={{ color: '#06b6d4' }} />
            <span>⚡ Recent Autonomous Agent Decisions & Execution Log</span>
          </h4>
          <span style={{ fontSize: '0.72rem', background: 'rgba(6, 182, 212, 0.15)', color: '#38bdf8', padding: '0.2rem 0.6rem', borderRadius: '4px', fontWeight: 700 }}>
            FLEET TELEMETRY
          </span>
        </div>
        <div className="admin-table-wrap" style={{ maxHeight: '380px', overflowY: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Agent Specialist</th>
                <th>Action Type</th>
                <th>Autonomous Execution Details</th>
              </tr>
            </thead>
            <tbody>
              {agentLogs.slice(0, 30).map((log, idx) => {
                const time = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : 'Recent';
                return (
                  <tr key={idx}>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{time}</td>
                    <td><strong style={{ color: '#22d3ee' }}>{log.agent_name}</strong></td>
                    <td>
                      <span style={{
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        padding: '0.15rem 0.45rem',
                        borderRadius: '4px',
                        background: 'rgba(255, 255, 255, 0.06)',
                        color: '#f8fafc'
                      }}>
                        {log.action_type || 'DECISION'}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.78rem', color: '#cbd5e1' }}>
                      {log.details || ''}
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

