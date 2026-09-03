import React from 'react';
import { ArrowDown, Sparkles, ShieldCheck, Zap } from 'lucide-react';
import { useStore } from '../../context/StoreContext';

export default function HeroSection({ onOpenNova, onExploreAgents }) {
  const { catalog } = useStore();
  const inStockCount = catalog.filter(p => (p.STOCK_REMAINING || 0) > 0).length;

  const scrollToCatalog = () => {
    const el = document.getElementById('catalog-grid-anchor');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <section className="nike-hero-banner">
      <div className="hero-kicker-tag">
        <Sparkles size={14} style={{ color: '#d4ff00' }} />
        <span>NAVA: AGENTIC AI STORE • 24/7 AUTONOMOUS COMMERCE</span>
      </div>

      <h1 className="hero-headline-massive">
        ENGINEERED FOR SUPREMACY.
      </h1>

      <p className="hero-subcopy">
        Next-gen 5G smartphones, M3 titanium workstations, and audiophile acoustics. 
        Continuously audited and dynamically priced by 7 autonomous AI agents running locally. 
        Zero tax storewide, 1-click Razorpay checkout.
      </p>

      <div className="hero-cta-group">
        <button 
          className="nike-pill-btn primary-black"
          onClick={scrollToCatalog}
        >
          <span>Shop Latest Drops</span>
          <ArrowDown size={16} />
        </button>

        <button 
          className="nike-pill-btn secondary-white"
          onClick={onExploreAgents}
        >
          <span>Meet the 7 AI Agents</span>
        </button>

        <button 
          className="nike-pill-btn accent-volt"
          onClick={onOpenNova}
        >
          <Zap size={16} />
          <span>Ask Nava Copilot</span>
        </button>
      </div>


      {/* Hero Stats Mini-Row */}
      <div style={{
        display: 'flex',
        gap: '2.5rem',
        marginTop: '3.5rem',
        borderTop: '1px solid #e5e5e5',
        paddingTop: '1.75rem',
        flexWrap: 'wrap',
        justifyContent: 'center'
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 900, color: '#111' }}>24/7</div>
          <div style={{ fontSize: '0.74rem', color: '#707072', textTransform: 'uppercase', fontWeight: 700 }}>Autonomous Cycles</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 900, color: '#2e7d32' }}>₹ 0.00</div>
          <div style={{ fontSize: '0.74rem', color: '#707072', textTransform: 'uppercase', fontWeight: 700 }}>Tax Storewide</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 900, color: '#111' }}>100%</div>
          <div style={{ fontSize: '0.74rem', color: '#707072', textTransform: 'uppercase', fontWeight: 700 }}>Base Floor Safe</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '2rem', fontWeight: 900, color: '#fa5400' }}>{inStockCount} / {catalog.length}</div>
          <div style={{ fontSize: '0.74rem', color: '#707072', textTransform: 'uppercase', fontWeight: 700 }}>SKUs Ready to Ship</div>
        </div>
      </div>
    </section>
  );
}
