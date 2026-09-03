import React, { useState, useEffect } from 'react';
import { Megaphone, PlusCircle, CheckCircle, TrendingUp, Clock, Zap, Play, Square, Trash2, ShieldCheck, AlertCircle } from 'lucide-react';
import { api } from '../../api/client';
import { useStore } from '../../context/StoreContext';

export default function CampaignsTab() {
  const { showToast, refreshCatalog } = useStore();
  const [campaigns, setCampaigns] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const [newTitle, setNewTitle] = useState('Midnight 5G Flash Drop');
  const [newCategory, setNewCategory] = useState('Mobiles');
  const [newDiscount, setNewDiscount] = useState(8.0);
  const [newDuration, setNewDuration] = useState(24);
  const [isLaunching, setIsLaunching] = useState(false);
  const [processingId, setProcessingId] = useState(null);

  const loadCampaigns = async () => {
    setIsLoading(true);
    try {
      const res = await api.getAdminCampaigns();
      if (res && res.campaigns) {
        setCampaigns(res.campaigns);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCampaigns();
  }, []);

  const handleLaunch = async (e) => {
    e.preventDefault();
    if (!newTitle.trim() || isLaunching) return;
    setIsLaunching(true);
    try {
      const res = await api.launchAdminCampaign({
        title: newTitle.trim(),
        category: newCategory,
        discount_percent: parseFloat(newDiscount),
        duration_hours: parseInt(newDuration)
      });

      if (res.success) {
        showToast(res.message || 'Campaign launched! (At most 1 active campaign per category rule enforced)', 'success');
        await Promise.all([loadCampaigns(), refreshCatalog()]);
      } else {
        showToast(res.error || 'Failed to launch campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setIsLaunching(false);
    }
  };

  const handleActivate = async (campaignId, category) => {
    setProcessingId(campaignId);
    try {
      const res = await api.activateAdminCampaign(campaignId);
      if (res.success) {
        showToast(res.message || `Campaign activated for ${category}!`, 'success');
        await Promise.all([loadCampaigns(), refreshCatalog()]);
      } else {
        showToast(res.error || 'Failed to activate campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setProcessingId(null);
    }
  };

  const handleStop = async (campaignId) => {
    setProcessingId(campaignId);
    try {
      const res = await api.stopAdminCampaign(campaignId);
      if (res.success) {
        showToast(res.message || 'Campaign stopped and regular prices restored!', 'info');
        await Promise.all([loadCampaigns(), refreshCatalog()]);
      } else {
        showToast(res.error || 'Failed to stop campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setProcessingId(null);
    }
  };

  const handleDelete = async (campaignId) => {
    if (!window.confirm('Delete this campaign from the orchestrator?')) return;
    setProcessingId(campaignId);
    try {
      const res = await api.deleteAdminCampaign(campaignId);
      if (res.success) {
        showToast('Campaign deleted successfully.', 'success');
        await Promise.all([loadCampaigns(), refreshCatalog()]);
      } else {
        showToast(res.error || 'Failed to delete campaign', 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      setProcessingId(null);
    }
  };

  // Compute active categories
  const activeCategories = campaigns
    .filter(c => c.status === 'ACTIVE')
    .map(c => c.category);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            ⚡ Promotional Campaign Orchestrator
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            Human Store Owner governs promotional flash sales. Strict Invariant: <strong>At most 1 active campaign per category</strong>. All discounts strictly respect the <strong>Base Price Floor</strong>.
          </p>
        </div>

        {/* Category Active Status Badges */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          {['Mobiles', 'Laptops', 'Audio', 'Accessories'].map(cat => {
            const hasActive = activeCategories.includes(cat) || activeCategories.includes('ALL');
            return (
              <span key={cat} style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                padding: '0.2rem 0.6rem',
                borderRadius: '6px',
                background: hasActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                color: hasActive ? '#34d399' : '#94a3b8',
                border: `1px solid ${hasActive ? 'rgba(16, 185, 129, 0.35)' : 'rgba(255, 255, 255, 0.08)'}`
              }}>
                {cat}: {hasActive ? '1 Active' : 'Idle'}
              </span>
            );
          })}
        </div>
      </div>

      {/* Launch New Campaign Card */}
      <div className="glass-panel">
        <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', textTransform: 'uppercase', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Zap size={18} style={{ color: '#fbbf24' }} />
          <span>Create or Launch Targeted Promotional Campaign</span>
        </h4>

        <form onSubmit={handleLaunch} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <label style={{ fontSize: '0.78rem', fontWeight: 700 }}>Campaign Title</label>
            <input 
              type="text"
              className="form-input"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Weekend Titanium Festival"
              required
            />
          </div>

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label style={{ fontSize: '0.78rem', fontWeight: 700 }}>Target Category</label>
            <select 
              className="form-select"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
            >
              <option value="ALL">All Categories</option>
              <option value="Mobiles">Mobiles</option>
              <option value="Laptops">Laptops</option>
              <option value="Audio">Audio</option>
              <option value="Accessories">Accessories</option>
            </select>
          </div>

          <div className="form-group" style={{ marginBottom: 0 }}>
            <label style={{ fontSize: '0.78rem', fontWeight: 700 }}>Discount % (Gated 1%-25%)</label>
            <input 
              type="number"
              step="0.5"
              min="1"
              max="25"
              className="form-input"
              value={newDiscount}
              onChange={(e) => setNewDiscount(e.target.value)}
              required
            />
          </div>

          <button 
            type="submit"
            className="action-btn primary"
            disabled={isLaunching}
            style={{ height: '40px', padding: '0 1.25rem', justifyContent: 'center' }}
          >
            <Megaphone size={15} />
            <span>{isLaunching ? 'Creating...' : 'Launch & Activate'}</span>
          </button>
        </form>
      </div>

      {/* Campaigns History Table */}
      <div className="glass-panel">
        <div className="panel-header-bar" style={{ padding: '1rem 1.25rem', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', textTransform: 'uppercase' }}>
            Store Campaigns ({campaigns.length}) — Owner Governance
          </h4>
          <span style={{ fontSize: '0.74rem', color: '#94a3b8' }}>
            Rule: At most 1 active campaign per category
          </span>
        </div>

        <div className="admin-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Campaign Name</th>
                <th>Category</th>
                <th>Discount</th>
                <th>Marquee Announcement</th>
                <th>Launched At</th>
                <th>Owner Controls</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((c) => {
                const isActive = c.status === 'ACTIVE';
                const isProcessing = processingId === c.id;

                return (
                  <tr key={c.id}>
                    <td>
                      <span style={{
                        fontSize: '0.72rem',
                        fontWeight: 800,
                        padding: '0.2rem 0.55rem',
                        borderRadius: '9999px',
                        background: isActive ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.08)',
                        color: isActive ? '#34d399' : '#94a3b8',
                        border: `1px solid ${isActive ? 'rgba(16, 185, 129, 0.4)' : 'rgba(255, 255, 255, 0.1)'}`
                      }}>
                        {c.status}
                      </span>
                    </td>
                    <td>
                      <strong style={{ color: '#fff' }}>{c.title}</strong>
                      <div style={{ fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'monospace' }}>{c.id}</div>
                    </td>
                    <td>
                      <span className="prod-badge-cat" style={{ position: 'static' }}>{c.category}</span>
                    </td>
                    <td>
                      <span style={{ fontWeight: 800, color: '#34d399', fontFamily: 'monospace' }}>
                        {c.discount_percent}% OFF
                      </span>
                    </td>
                    <td style={{ fontSize: '0.78rem', color: '#e2e8f0', maxWidth: '280px' }}>
                      {c.banner_text}
                    </td>
                    <td style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                      {new Date(c.launched_at).toLocaleDateString()}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                        {!isActive ? (
                          <button 
                            className="action-btn"
                            style={{ 
                              padding: '0.25rem 0.6rem', 
                              fontSize: '0.72rem', 
                              color: '#34d399', 
                              background: 'rgba(16, 185, 129, 0.12)', 
                              borderColor: 'rgba(16, 185, 129, 0.35)' 
                            }}
                            onClick={() => handleActivate(c.id, c.category)}
                            disabled={isProcessing}
                            title={`Activate this campaign (deactivates any other active campaign in ${c.category})`}
                          >
                            <Play size={11} />
                            <span>Activate</span>
                          </button>
                        ) : (
                          <button 
                            className="action-btn"
                            style={{ 
                              padding: '0.25rem 0.6rem', 
                              fontSize: '0.72rem', 
                              color: '#fbbf24', 
                              background: 'rgba(245, 158, 11, 0.12)', 
                              borderColor: 'rgba(245, 158, 11, 0.35)' 
                            }}
                            onClick={() => handleStop(c.id)}
                            disabled={isProcessing}
                            title="Stop campaign and restore regular prices"
                          >
                            <Square size={11} />
                            <span>Stop</span>
                          </button>
                        )}

                        <button 
                          className="action-btn danger"
                          style={{ 
                            padding: '0.25rem 0.5rem', 
                            fontSize: '0.72rem', 
                            color: '#fb7185', 
                            background: 'rgba(244, 63, 94, 0.12)', 
                            borderColor: 'rgba(244, 63, 94, 0.35)' 
                          }}
                          onClick={() => handleDelete(c.id)}
                          disabled={isProcessing}
                          title="Delete campaign"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
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


