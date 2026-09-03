import React from 'react';
import { 
  LayoutDashboard, 
  Wallet, 
  Users, 
  Bot, 
  ShoppingCart, 
  Package, 
  RotateCcw, 
  Star, 
  Sparkles, 
  Crown, 
  Building2, 
  ExternalLink,
  Megaphone,
  ShieldCheck 
} from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';

export default function AdminSidebar({ onOpenStorefront }) {
  const { activeTab, setActiveTab, overview, treasury, setIsResetConfirmModalOpen } = useAdmin();

  const bankBalance = treasury?.bank_balance ?? overview?.kpis?.total_revenue ?? 500000;
  const formattedBalance = bankBalance >= 100000 
    ? `₹${(bankBalance / 1000).toFixed(0)}K` 
    : `₹${bankBalance.toFixed(0)}`;

  const tabs = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'campaigns', label: 'Campaign Orchestrator', icon: Megaphone, badge: 'Flash Promo', badgeColor: 'amber' },
    { id: 'audit', label: 'Audit Trail & Bounds', icon: ShieldCheck },
    { id: 'treasury', label: 'CEO Treasury & Salaries', icon: Wallet, badge: formattedBalance, badgeColor: 'emerald' },
    { id: 'buyers', label: '5 AI Shoppers Fleet', icon: Users, badge: '5 Active', badgeColor: 'purple' },
    { id: 'agents', label: '24/7 Agent Fleet', icon: Bot, badge: '7 Active', badgeColor: 'blue' },
    { id: 'orders', label: 'Orders & Dispatch', icon: ShoppingCart },
    { id: 'inventory', label: 'Inventory & Dual-Pricing', icon: Package },
    { id: 'refunds', label: 'Refunds & 24h Policy', icon: RotateCcw },
    { id: 'reviews', label: 'AI Reviews & Feedback', icon: Star },
    { id: 'chat', label: 'CEO Command Chat', icon: Sparkles }
  ];

  return (
    <aside className="admin-sidebar">
      <div className="sidebar-title-box">
        <div className="sidebar-crown-icon">
          <Crown size={18} />
        </div>
        <div>
          <h3>COMMAND CENTER</h3>
          <span>24/7 Autonomous Store</span>
        </div>
      </div>

      {/* 7 AI Agents Active indicator */}
      <div style={{
        background: 'rgba(168, 85, 247, 0.12)',
        border: '1px solid rgba(168, 85, 247, 0.3)',
        borderRadius: '10px',
        padding: '0.65rem 0.85rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.65rem'
      }}>
        <span className="pulse-dot"></span>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <strong style={{ fontSize: '0.76rem', color: '#c084fc', letterSpacing: '0.02em' }}>7 AI AGENTS ACTIVE</strong>
          <span style={{ fontSize: '0.66rem', color: '#94a3b8' }}>Closed-Loop Mesh Ticker</span>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="sidebar-nav-list">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`nav-tab-btn ${isActive ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <div className="nav-tab-left">
                <Icon size={16} style={{ color: isActive ? 'var(--cyan-400)' : 'inherit' }} />
                <span>{tab.label}</span>
              </div>
              {tab.badge && (
                <span className={`tab-badge ${tab.badgeColor || 'emerald'}`}>
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer Links & Reset */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', paddingTop: '0.75rem', borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
        <button 
          className="action-btn danger"
          style={{ 
            background: 'rgba(244, 63, 94, 0.12)', 
            borderColor: 'rgba(244, 63, 94, 0.35)', 
            color: '#fb7185', 
            justifyContent: 'center',
            fontSize: '0.75rem'
          }}
          onClick={() => setIsResetConfirmModalOpen(true)}
          title="Reset inventory to 0 stock, clear orders, reset bank balance"
        >
          <RotateCcw size={14} />
          <span>Reset to Base Condition</span>
        </button>

        <a 
          href="/office" 
          target="_blank" 
          rel="noopener noreferrer"
          className="action-btn"
          style={{ 
            background: 'rgba(168, 85, 247, 0.15)', 
            borderColor: 'rgba(168, 85, 247, 0.35)', 
            color: '#c084fc', 
            justifyContent: 'center',
            textDecoration: 'none'
          }}
        >
          <Building2 size={15} />
          <span>🏢 Open Agents Office</span>
        </a>

        <button 
          className="action-btn"
          style={{ justifyContent: 'center' }}
          onClick={onOpenStorefront}
        >
          <ExternalLink size={15} />
          <span>Open Live Storefront</span>
        </button>
      </div>
    </aside>
  );
}

