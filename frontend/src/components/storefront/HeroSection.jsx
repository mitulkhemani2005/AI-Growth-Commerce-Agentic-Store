import React from 'react';
import { ArrowRight, Sparkles, ShieldCheck, Truck, Cpu } from 'lucide-react';
import { useStore } from '../../context/StoreContext';

export default function HeroSection({ onOpenNova, onExploreAgents }) {
  const { serviceStatus } = useStore();
  const shop = () => document.getElementById('catalog-grid-anchor')?.scrollIntoView({ behavior: 'smooth' });
  return <>
    <section className="store-hero page-width">
      <div className="hero-copy">
        <span className="eyebrow"><span className="little-line" /> A BETTER KIND OF TECH STORE</span>
        <h1>Great tech.<br /><em>Zero guesswork.</em></h1>
        <p>The devices you love. A store that thinks ahead. Discover your next upgrade with a little help from Nova.</p>
        <div className="hero-actions"><button className="button button-dark" onClick={shop}>Explore the collection<ArrowRight size={17} /></button><button className="button button-link" onClick={onOpenNova}><Sparkles size={16} />Ask Nova</button></div>
        <div className="hero-proof"><span className="avatar-stack"><b>N</b><b>✳</b><b>AI</b></span><span><strong>7 specialist agents. One seamless store.</strong><small>{serviceStatus?.background_agents_enabled ? 'Working together, around the clock.' : 'Inventory, pricing, fulfillment, and more.'}</small></span></div>
      </div>
      <div className="hero-art" aria-label="Featured Nova technology">
        <span className="art-caption">CURATED FOR YOUR EVERYDAY</span><span className="art-circle" />
        <img className="hero-laptop" src="/static/images/laptop_pro.svg" alt="Nova laptop" />
        <img className="hero-phone" src="/static/images/phone_flagship.svg" alt="Nova flagship phone" />
        <div className="floating-note"><span className="note-icon"><Sparkles size={18} /></span><div><strong>A smarter match.</strong><small>Picked for the way you live.</small></div></div>
        <button className="art-bottom" onClick={onExploreAgents}><span><i /> Intelligence, behind the scenes.</span><ArrowRight size={16} /></button>
      </div>
    </section>
    <div className="benefit-strip page-width"><span><Truck size={19} /><b>Free delivery</b><small>On every order</small></span><span><ShieldCheck size={19} /><b>Shop with confidence</b><small>Clear checkout and order tracking</small></span><span><Cpu size={19} /><b>Locally powered AI</b><small>{serviceStatus?.gpu?.gpu_resident ? 'Running on your GPU' : 'Your personal shopping copilot'}</small></span></div>
  </>;
}
