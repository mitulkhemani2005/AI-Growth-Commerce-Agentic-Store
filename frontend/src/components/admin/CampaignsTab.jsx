import React, { useState, useEffect } from 'react';
import { Megaphone, PlusCircle, CheckCircle, Radio, TrendingUp, Clock, Zap } from 'lucide-react';
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
        showToast(res.message || 'Campaign launched and broadcast to message bus!', 'success');
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.75rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#111' }}>
            ⚡ Autonomous Campaign Orchestrator Agent
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#707072' }}>
            Schedules and launches promotional flash sales, adjusts prices within the immutable <strong>Base Price Floor</strong>, broadcasts to the <strong>Inter-Agent Message Bus</strong>, and pings the 5 AI Shoppers.
          </p>
        </div>
      </div>

      {/* Launch New Campaign Card */}
      <div className="nike-table-card" style={{ padding: '1.5rem' }}>
        <h4 style={{ fontFamily: 'var(--font-display)', fontSize: '1.15rem', color: '#111', textTransform: 'uppercase', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Zap size={18} style={{ color: '#d4ff00' }} />
          <span>Launch Targeted Promotional Campaign</span>
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
            className="nike-pill-btn primary-black"
            disabled={isLaunching}
            style={{ height: '42px', padding: '0 1.25rem' }}
          >
            <Megaphone size={15} />
            <span>{isLaunching ? 'Broadcasting...' : 'Launch & Broadcast'}</span>
          </button>
        </form>
      </div>

      {/* Campaigns History Table */}
      <div className="nike-table-card">
        <table className="nike-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Campaign Name</th>
              <th>Category</th>
              <th>Discount</th>
              <th>Marquee Announcement</th>
              <th>Launched At</th>
            </tr>
          </thead>
          <tbody>
            {campaigns.map((c) => {
              const isActive = c.status === 'ACTIVE';
              return (
                <tr key={c.id}>
                  <td>
                    <span style={{
                      fontSize: '0.72rem',
                      fontWeight: 800,
                      padding: '0.2rem 0.55rem',
                      borderRadius: '9999px',
                      background: isActive ? '#dcfce7' : '#f3f4f6',
                      color: isActive ? '#15803d' : '#707072'
                    }}>
                      {c.status}
                    </span>
                  </td>
                  <td>
                    <strong style={{ color: '#111' }}>{c.title}</strong>
                    <div style={{ fontSize: '0.72rem', color: '#707072', fontFamily: 'monospace' }}>{c.id}</div>
                  </td>
                  <td>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>{c.category}</span>
                  </td>
                  <td>
                    <span style={{ fontWeight: 800, color: '#15803d', fontFamily: 'monospace' }}>
                      {c.discount_percent}% OFF
                    </span>
                  </td>
                  <td style={{ fontSize: '0.78rem', color: '#111', maxWidth: '300px' }}>
                    {c.banner_text}
                  </td>
                  <td style={{ fontSize: '0.75rem', color: '#707072' }}>
                    {new Date(c.launched_at).toLocaleDateString()}
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
