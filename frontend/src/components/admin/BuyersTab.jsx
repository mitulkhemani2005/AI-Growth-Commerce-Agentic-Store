import React, { useState } from 'react';
import { 
  Users, 
  ShoppingBag, 
  Power, 
  Play, 
  Sparkles, 
  CheckCircle, 
  Clock, 
  Activity 
} from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';

export default function BuyersTab() {
  const { buyers, loadAllAdminData } = useAdmin();
  const { refreshCatalog, refreshOrders, showToast } = useStore();

  const [isSimActive, setIsSimActive] = useState(true);
  const [triggeringId, setTriggeringId] = useState(null);
  const [fleetInterval, setFleetInterval] = useState(60);
  const [buyerIntervals, setBuyerIntervals] = useState({});
  const [savingIntervalId, setSavingIntervalId] = useState(null);

  // Toggle master simulation
  const handleToggleSimulation = async () => {
    try {
      const res = await api.toggleAIBuyers();
      setIsSimActive(res.enabled);
      showToast(res.message || 'Simulation state updated', 'info');
      await loadAllAdminData();
    } catch (e) {
      showToast(e.message, 'error');
    }
  };

  // Trigger individual or all buyers
  const handleTriggerBuyer = async (buyerId = 'all') => {
    setTriggeringId(buyerId);
    try {
      const res = await api.triggerAIBuyer(buyerId);
      showToast(res.message || `Triggered shopper step for ${buyerId}!`, 'success');
      await Promise.all([loadAllAdminData(), refreshCatalog(), refreshOrders()]);
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setTriggeringId(null);
    }
  };

  // Update interval
  const handleUpdateInterval = async (buyerId = 'all', explicitVal = null) => {
    const rawVal = explicitVal !== null ? explicitVal : (buyerId === 'all' ? fleetInterval : buyerIntervals[buyerId]);
    const val = parseInt(rawVal);
    if (!val || val < 5) {
      showToast('Interval must be at least 5 seconds', 'error');
      return;
    }

    setSavingIntervalId(buyerId);
    try {
      const res = await api.updateBuyerInterval(buyerId, val);
      if (buyerId === 'all') setFleetInterval(val);
      showToast(res.message || `Shopper interval set to ${val}s!`, 'success');
      await loadAllAdminData();
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setSavingIntervalId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      {/* Intro & Master Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            🛍️ 5 AI Autonomous Shoppers Fleet
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            5 distinct AI consumer personas with <strong>unlimited budgets</strong> continuously browse the catalog, purchase via 1-click AP2 protocol, publish reviews, and stress-test 24h refund policies.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button 
            className="action-btn"
            style={{ 
              background: isSimActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              borderColor: isSimActive ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.4)',
              color: isSimActive ? '#34d399' : '#fb7185'
            }}
            onClick={handleToggleSimulation}
          >
            <Power size={15} />
            <span>Simulation: {isSimActive ? 'ACTIVE' : 'PAUSED'}</span>
          </button>

          <button 
            className="action-btn primary"
            onClick={() => handleTriggerBuyer('all')}
            disabled={triggeringId === 'all'}
          >
            <ShoppingBag size={15} />
            <span>{triggeringId === 'all' ? 'Triggering Fleet...' : 'Trigger All 5 Shoppers Now'}</span>
          </button>
        </div>
      </div>

      {/* Fleet Browsing Interval Control Panel */}
      <div className="glass-panel" style={{ padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <Clock size={18} style={{ color: '#c084fc' }} />
          <div>
            <strong style={{ fontSize: '0.9rem', color: '#fff' }}>Autonomous Fleet Browsing Schedule</strong>
            <div style={{ fontSize: '0.74rem', color: '#94a3b8' }}>Control how frequently AI personas make autonomous purchase and evaluation runs.</div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Presets:</span>
          {[30, 60, 120, 300].map(sec => (
            <button
              key={sec}
              type="button"
              className="action-btn"
              style={{
                padding: '0.2rem 0.55rem',
                fontSize: '0.72rem',
                background: fleetInterval === sec ? 'rgba(192, 132, 252, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                borderColor: fleetInterval === sec ? 'rgba(192, 132, 252, 0.5)' : 'rgba(255, 255, 255, 0.1)',
                color: fleetInterval === sec ? '#c084fc' : '#94a3b8'
              }}
              onClick={() => handleUpdateInterval('all', sec)}
            >
              {sec}s
            </button>
          ))}

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: '0.5rem' }}>
            <input 
              type="number"
              min="5"
              max="3600"
              className="form-input"
              style={{ width: '80px', padding: '0.35rem 0.5rem', fontSize: '0.8rem' }}
              value={fleetInterval}
              onChange={(e) => setFleetInterval(e.target.value)}
            />
            <button 
              className="action-btn"
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.75rem' }}
              onClick={() => handleUpdateInterval('all')}
              disabled={savingIntervalId === 'all'}
            >
              {savingIntervalId === 'all' ? 'Saving...' : 'Set Fleet Interval'}
            </button>
          </div>
        </div>
      </div>

      {/* 5 AI Buyer Persona Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '1.25rem'
      }}>
        {buyers.map((buyer) => {
          const buyerInterval = buyerIntervals[buyer.id] !== undefined 
            ? buyerIntervals[buyer.id] 
            : (buyer.interval_seconds || 60);

          return (
            <div 
              key={buyer.id}
              className="product-card"
              style={{ padding: '1.25rem', gap: '0.85rem', display: 'flex', flexDirection: 'column' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span style={{ fontSize: '2rem' }}>{buyer.avatar || '🤖'}</span>
                  <div>
                    <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff' }}>{buyer.name}</h4>
                    <span style={{ fontSize: '0.72rem', color: '#c084fc', fontWeight: 600 }}>
                      {buyer.persona_title}
                    </span>
                  </div>
                </div>

                <span style={{
                  fontSize: '0.68rem',
                  fontWeight: 700,
                  background: 'rgba(6, 182, 212, 0.15)',
                  color: '#22d3ee',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '9999px'
                }}>
                  AP2 Auto-Pay
                </span>
              </div>

              <p style={{ fontSize: '0.78rem', color: '#94a3b8', lineHeight: 1.4 }}>
                {buyer.description}
              </p>

              <div style={{
                background: 'rgba(8, 12, 21, 0.6)',
                borderRadius: '8px',
                padding: '0.75rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.35rem',
                fontSize: '0.76rem',
                border: '1px solid rgba(255, 255, 255, 0.05)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Preferred:</span>
                  <strong style={{ color: '#fff' }}>{(buyer.preferred_categories || []).join(', ')}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Total Spent:</span>
                  <strong style={{ color: '#34d399', fontFamily: 'monospace' }}>
                    ₹{Number(buyer.total_spent || 0).toFixed(2)}
                  </strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Orders / Returns:</span>
                  <strong style={{ color: '#cbd5e1' }}>
                    {buyer.orders_count || 0} orders • {buyer.returns_count || 0} returns
                  </strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Cycle Interval:</span>
                  <strong style={{ color: '#c084fc' }}>
                    Every {buyer.interval_seconds || 60}s
                  </strong>
                </div>
              </div>

              {/* Individual Shopper Interval Row */}
              <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                <input 
                  type="number"
                  min="5"
                  max="3600"
                  className="form-input"
                  style={{ width: '75px', padding: '0.3rem 0.5rem', fontSize: '0.75rem' }}
                  value={buyerInterval}
                  onChange={(e) => setBuyerIntervals({ ...buyerIntervals, [buyer.id]: e.target.value })}
                />
                <button
                  className="action-btn"
                  style={{ padding: '0.3rem 0.6rem', fontSize: '0.72rem' }}
                  onClick={() => handleUpdateInterval(buyer.id)}
                  disabled={savingIntervalId === buyer.id}
                >
                  {savingIntervalId === buyer.id ? 'Saving...' : 'Set Interval'}
                </button>
              </div>

              <div style={{ fontSize: '0.74rem', color: '#34d399', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Clock size={12} />
                <span>{buyer.status || 'Browsing catalog'}</span>
              </div>

              <button 
                className="action-btn"
                style={{ width: '100%', justifyContent: 'center', marginTop: 'auto' }}
                onClick={() => handleTriggerBuyer(buyer.id)}
                disabled={triggeringId === buyer.id}
              >
                <Play size={13} />
                <span>{triggeringId === buyer.id ? 'Executing Step...' : 'Trigger Shopper Step'}</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

