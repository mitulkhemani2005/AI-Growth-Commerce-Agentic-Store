import React, { useState, useEffect } from 'react';
import { 
  Sparkles, 
  Search, 
  ShoppingBag, 
  ClipboardList, 
  CreditCard, 
  Crown, 
  Building2, 
  User, 
  ChevronDown,
  ShieldCheck,
  Zap
} from 'lucide-react';
import { useStore } from '../../context/StoreContext';
import { useAdmin } from '../../context/AdminContext';
import { api } from '../../api/client';

export default function Header({ currentView, setCurrentView, activeCategory, setActiveCategory }) {
  const { 
    currentUser, 
    cart, 
    orders, 
    setIsCartOpen, 
    setIsOrdersOpen, 
    setIsRzpModalOpen, 
    setIsUserModalOpen 
  } = useStore();

  const { overview } = useAdmin();
  const [activeCampaign, setActiveCampaign] = useState(null);

  useEffect(() => {
    api.getActiveCampaign()
      .then(res => {
        if (res && res.campaign) setActiveCampaign(res.campaign);
      })
      .catch(() => {});
  }, []);

  const cartItemCount = cart?.item_count || 0;
  const ordersCount = orders?.length || 0;

  const categories = [
    { id: 'ALL', label: 'All Products' },
    { id: 'Mobiles', label: 'Mobiles' },
    { id: 'Laptops', label: 'Laptops' },
    { id: 'Audio', label: 'Audio Gear' },
    { id: 'Accessories', label: 'Accessories' }
  ];

  return (
    <header style={{ position: 'sticky', top: 0, zIndex: 120 }}>
      {/* Tier 1: Sub-Utility Bar */}
      <div className="nike-utility-bar">
        <div className="utility-left">
          <a 
            href="/office" 
            target="_blank" 
            rel="noopener noreferrer"
            className="utility-brand-link"
            title="Launch AgentsOffice Pixel RPG Live Simulation"
          >
            <Building2 size={13} style={{ color: '#a855f7' }} />
            <span>Agents Office RPG Simulator</span>
          </a>
          <span style={{ color: '#d1d5db' }}>|</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#10b981' }}>
            <span className="pulse-dot emerald" style={{ width: '6px', height: '6px' }}></span>
            <span>7 Autonomous Fleet Active</span>
          </span>
        </div>

        <div className="utility-right">
          <span 
            className="utility-item" 
            onClick={() => setIsRzpModalOpen(true)}
            title="Configure Razorpay Credentials"
          >
            <CreditCard size={13} />
            <span>Razorpay Gateway</span>
          </span>

          <span style={{ color: '#d1d5db' }}>|</span>

          {/* User Switcher */}
          <span 
            className="utility-item" 
            onClick={() => setIsUserModalOpen(true)}
            title="Switch Active Customer Profile"
          >
            <User size={13} />
            <span>Hi, {currentUser.name.split(' ')[0]}</span>
            <ChevronDown size={12} />
          </span>

          <span style={{ color: '#d1d5db' }}>|</span>

          {/* Owner Command Switch */}
          <button 
            className="admin-mode-pill-btn"
            onClick={() => setCurrentView(currentView === 'admin' ? 'store' : 'admin')}
            title="Switch between Storefront & Owner Command Studio"
          >
            <Crown size={12} style={{ color: '#d4ff00' }} />
            <span>{currentView === 'admin' ? 'Back to Storefront' : 'Owner Studio'}</span>
          </button>
        </div>
      </div>

      {/* Tier 2: Main Sticky Nav */}
      <div className="nike-main-nav">
        {/* Brand Mark */}
        <div 
          className="nike-logo-box" 
          onClick={() => setCurrentView('store')}
          style={{ cursor: 'pointer' }}
        >
          <div className="nike-brand-title">
            <span>NAVA</span>
            <span className="volt-pill">AGENTIC AI</span>
          </div>
        </div>


        {/* Categories Center Links */}
        {currentView === 'store' && (
          <nav className="nike-nav-categories">
            {categories.map(cat => (
              <button
                key={cat.id}
                className={`nav-cat-link ${activeCategory === cat.id ? 'active' : ''}`}
                onClick={() => {
                  setActiveCategory(cat.id);
                  const el = document.getElementById('catalog-grid-anchor');
                  if (el) el.scrollIntoView({ behavior: 'smooth' });
                }}
              >
                {cat.label}
              </button>
            ))}
          </nav>
        )}

        {/* Right Tools: Orders, Bag */}
        <div className="nike-nav-right">
          {currentView === 'store' && (
            <>
              {/* Orders Button */}
              <button 
                className="nike-icon-btn" 
                onClick={() => setIsOrdersOpen(true)}
                title="View Orders & Real-Time Tracking"
              >
                <ClipboardList size={20} />
                {ordersCount > 0 && <span className="nike-bag-badge">{ordersCount}</span>}
              </button>

              {/* Shopping Bag Button */}
              <button 
                className="nike-icon-btn" 
                onClick={() => setIsCartOpen(true)}
                title="Open Shopping Bag"
              >
                <ShoppingBag size={20} />
                {cartItemCount > 0 && <span className="nike-bag-badge">{cartItemCount}</span>}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tier 3: Animated Marquee Announcement Ticker */}
      <div className="nike-announcement-marquee">
        <div className="marquee-inner">
          {activeCampaign?.banner_text && (
            <div className="marquee-item">
              <span className="volt">🔥 PROMO:</span>
              <span style={{ color: '#d4ff00', fontWeight: 800 }}>{activeCampaign.banner_text}</span>
            </div>
          )}
          <div className="marquee-item">
            <span className="volt">● 0% TAX STOREWIDE</span>
            <span>Standardized in Indian Rupees (₹ INR)</span>
          </div>
          <div className="marquee-item">
            <span className="volt">● 7 AUTONOMOUS SPECIALIST AI AGENTS</span>
            <span>Continuous Dynamic Pricing, Stock Auditing & Carrier Dispatch</span>
          </div>
          <div className="marquee-item">
            <span className="volt">● AGENTIC PAYMENTS (AP2)</span>
            <span>1-Click Autonomous Tokenized Checkout on Razorpay Rails</span>
          </div>
          <div className="marquee-item">
            <span className="volt">● 24-HOUR REFUND GOVERNANCE</span>
            <span>Pre-Shipment Auto-Approval with Immediate Warehouse Restock</span>
          </div>
          {/* Repeat for loop */}
          {activeCampaign?.banner_text && (
            <div className="marquee-item">
              <span className="volt">🔥 PROMO:</span>
              <span style={{ color: '#d4ff00', fontWeight: 800 }}>{activeCampaign.banner_text}</span>
            </div>
          )}
          <div className="marquee-item">
            <span className="volt">● 0% TAX STOREWIDE</span>
            <span>Standardized in Indian Rupees (₹ INR)</span>
          </div>
        </div>
      </div>
    </header>
  );
}

