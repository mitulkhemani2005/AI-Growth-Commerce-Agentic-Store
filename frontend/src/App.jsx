import React, { useState, useEffect } from 'react';
import { StoreProvider, useStore } from './context/StoreContext';
import { AdminProvider, useAdmin } from './context/AdminContext';

// Shared
import Header from './components/shared/Header';

// Storefront Components
import HeroSection from './components/storefront/HeroSection';
import FeaturedCarousel from './components/storefront/FeaturedCarousel';
import ProductCatalog from './components/storefront/ProductCatalog';
import InnovationStories from './components/storefront/InnovationStories';
import NavaCopilot from './components/storefront/NavaCopilot';
import CartDrawer from './components/storefront/CartDrawer';
import OrdersModal from './components/storefront/OrdersModal';
import RazorpayConfigModal from './components/storefront/RazorpayConfigModal';
import UserSwitchModal from './components/storefront/UserSwitchModal';

// Admin Components
import AdminSidebar from './components/admin/AdminSidebar';
import OverviewTab from './components/admin/OverviewTab';
import CampaignsTab from './components/admin/CampaignsTab';
import AuditTrailTab from './components/admin/AuditTrailTab';
import TreasuryTab from './components/admin/TreasuryTab';
import BuyersTab from './components/admin/BuyersTab';
import AgentsTab from './components/admin/AgentsTab';
import OrdersTab from './components/admin/OrdersTab';
import InventoryTab from './components/admin/InventoryTab';
import RefundsTab from './components/admin/RefundsTab';
import ReviewsTab from './components/admin/ReviewsTab';
import CEOChatTab from './components/admin/CEOChatTab';
import SalaryNegotiationModal from './components/admin/SalaryNegotiationModal';
import AddProductModal from './components/admin/AddProductModal';
import BulkPriceModal from './components/admin/BulkPriceModal';
import ResetStoreModal from './components/admin/ResetStoreModal';


function MainApp() {
  const [currentView, setCurrentView] = useState(() => {
    return window.location.pathname.startsWith('/admin') ? 'admin' : 'store';
  });

  const [activeCategory, setActiveCategory] = useState('ALL');
  const [isNovaOpen, setIsNovaOpen] = useState(false);

  const { toastMessage } = useStore();
  const { activeTab } = useAdmin();

  useEffect(() => {
    const targetPath = currentView === 'admin' ? '/admin' : '/';
    if (window.location.pathname !== targetPath && window.history.pushState) {
      window.history.pushState(null, '', targetPath);
    }
  }, [currentView]);

  return (
    <div className="app-container">
      {/* Toast Alert Banner */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          top: '90px',
          right: '24px',
          zIndex: 999,
          background: toastMessage.type === 'error' ? '#fa5400' : '#111111',
          color: '#ffffff',
          padding: '0.75rem 1.25rem',
          borderRadius: '9999px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
          fontSize: '0.85rem',
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          animation: 'fade-in 0.2s ease-out'
        }}>
          <span>{toastMessage.msg}</span>
        </div>
      )}

      {/* Nike 3-Tier Header */}
      <Header 
        currentView={currentView} 
        setCurrentView={setCurrentView}
        activeCategory={activeCategory}
        setActiveCategory={setActiveCategory}
      />

      {/* View 1: Customer Storefront (Nike-Style Editorial) */}
      {currentView === 'store' && (
        <main>
          {/* Hero Editorial Banner */}
          <HeroSection 
            onOpenNova={() => setIsNovaOpen(true)}
            onExploreAgents={() => {
              const el = document.getElementById('innovation-stories-anchor');
              if (el) el.scrollIntoView({ behavior: 'smooth' });
            }}
          />

          {/* Featured Drops Horizontal Snap Carousel */}
          <FeaturedCarousel />

          {/* Main Product Catalog & Sticky Sub-Filters */}
          <ProductCatalog 
            activeCategory={activeCategory}
            setActiveCategory={setActiveCategory}
          />

          {/* Innovation Stories Section (The 7 Autonomous Agents) */}
          <InnovationStories 
            onOpenNova={() => setIsNovaOpen(true)}
          />

          {/* Floating Athletic Nava AI Copilot Capsule & Flyout */}
          <NavaCopilot 
            isOpen={isNovaOpen}
            setIsOpen={setIsNovaOpen}
          />

          {/* Modals & Drawers */}
          <CartDrawer />
          <OrdersModal />
          <RazorpayConfigModal />
          <UserSwitchModal />
        </main>
      )}

      {/* View 2: Store Owner Command Studio */}
      {currentView === 'admin' && (
        <div className="admin-layout" style={{ background: '#fbfbfb' }}>
          <AdminSidebar onOpenStorefront={() => setCurrentView('store')} />
          <section className="admin-main-view" style={{ color: '#111' }}>
            {activeTab === 'overview' && <OverviewTab />}
            {activeTab === 'campaigns' && <CampaignsTab />}
            {activeTab === 'audit' && <AuditTrailTab />}
            {activeTab === 'treasury' && <TreasuryTab />}
            {activeTab === 'buyers' && <BuyersTab />}
            {activeTab === 'agents' && <AgentsTab />}
            {activeTab === 'orders' && <OrdersTab />}
            {activeTab === 'inventory' && <InventoryTab />}
            {activeTab === 'refunds' && <RefundsTab />}
            {activeTab === 'reviews' && <ReviewsTab />}
            {activeTab === 'chat' && <CEOChatTab />}
          </section>


          {/* Admin Modals */}
          <SalaryNegotiationModal />
          <AddProductModal />
          <BulkPriceModal />
          <ResetStoreModal />
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <AdminProvider>
        <MainApp />
      </AdminProvider>
    </StoreProvider>
  );
}
