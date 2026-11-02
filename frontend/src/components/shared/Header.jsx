import React from 'react';
import { ArrowUpRight, ShoppingBag, UserRound, Package, LayoutGrid, Sparkles } from 'lucide-react';
import { useStore } from '../../context/StoreContext';

export default function Header({ currentView, setCurrentView }) {
  const { cart, currentUser, serviceStatus, setIsCartOpen, setIsOrdersOpen, setIsUserModalOpen } = useStore();
  return <>
    <div className="announcement"><span>Thoughtfully selected. Intelligently managed.</span><span>Demo workspace · Payments are simulated</span></div>
    <header className="site-header">
      <button className="brand" onClick={() => setCurrentView('store')} aria-label="Nova home"><span className="brand-symbol">✳</span>nova<span className="brand-period">.</span></button>
      <nav className="main-nav" aria-label="Main navigation">
        <button className={currentView === 'store' ? 'selected' : ''} onClick={() => setCurrentView('store')}>The collection</button>
        <button className={currentView === 'admin' ? 'selected' : ''} onClick={() => setCurrentView('admin')}><LayoutGrid size={15} />Operations</button>
        <a href="/office/" target="_blank" rel="noreferrer">Agent office<ArrowUpRight size={13} /></a>
      </nav>
      <div className="header-actions">
        <span className={`connection-pill ${serviceStatus?.background_agents_enabled ? 'online' : ''}`}><i />{serviceStatus?.background_agents_enabled ? 'Agents online' : serviceStatus ? 'Store online' : 'Connecting'}</span>
        {currentView === 'store' && <>
          <button className="icon-button" onClick={() => setIsOrdersOpen(true)} aria-label="View orders"><Package size={20} /></button>
          <button className="icon-button bag-toggle" onClick={() => setIsCartOpen(true)} aria-label="Open shopping bag"><ShoppingBag size={20} />{cart.item_count > 0 && <span className="count-badge">{cart.item_count}</span>}</button>
        </>}
        <button className="profile-button" onClick={() => setIsUserModalOpen(true)} aria-label="Switch customer profile"><UserRound size={16} /><span>{currentUser.name.split(' ')[0]}</span></button>
      </div>
    </header>
    {currentView === 'admin' && <div className="workspace-bar"><span><Sparkles size={13} /> YOUR COMMERCE WORKSPACE</span><span>Live inventory · Local intelligence · Clear decisions</span></div>}
  </>;
}
