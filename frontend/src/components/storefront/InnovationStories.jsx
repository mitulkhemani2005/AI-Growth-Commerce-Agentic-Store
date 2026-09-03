import React from 'react';
import { Zap, ShieldCheck, Cpu, ArrowRight } from 'lucide-react';

export default function InnovationStories({ onOpenNova, onExploreAgents }) {
  const stories = [
    {
      num: '01',
      title: 'DUAL-TIER PRICING ENGINE',
      desc: 'The Store Owner locks an immutable Base Price Floor. The Price Manager Agent autonomously surcharges or discounts selling price based on warehouse velocity and real-time competitor demand signals.',
      accent: 'Owner Safe'
    },
    {
      num: '02',
      title: '7 AUTONOMOUS LOCAL AI AGENTS',
      desc: 'Inventory Manager, Order Tracker, Carrier Dispatcher, Finance Auditor, Sentiment Synthesizer, and CEO Agent communicate 24/7 over an asynchronous JSON message bus without human intervention.',
      accent: '24/7 Fleet'
    },
    {
      num: '03',
      title: 'AGENTIC PAYMENTS PROTOCOL (AP2)',
      desc: 'Cryptographically signed mandates enable Customer Copilot Nova to execute transactions autonomously on Razorpay rails without interrupting you with modal popups.',
      accent: 'Tokenized'
    },
    {
      num: '04',
      title: 'STRICT 24-HOUR REFUND GOVERNANCE',
      desc: 'Automated 1-click refund approval for any cancellation requested within 24 hours of creation prior to logistics dispatch. Stock restores instantly to inventory.',
      accent: 'Automated'
    }
  ];

  return (
    <section className="editorial-stories-section" id="innovation-stories-anchor">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
        <div>
          <span style={{ fontSize: '0.82rem', fontWeight: 800, color: '#707072', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            The Technology
          </span>
          <h2 className="editorial-heading-huge" style={{ marginBottom: 0 }}>
            INNOVATION LAB.
          </h2>
        </div>

        <a 
          href="/office" 
          target="_blank" 
          rel="noopener noreferrer"
          className="nike-pill-btn secondary-white"
          style={{ fontSize: '0.85rem', padding: '0.6rem 1.4rem' }}
        >
          <span>Launch Agents Office RPG Simulator</span>
          <ArrowRight size={15} />
        </a>
      </div>

      <div className="stories-grid-3col">
        {stories.map((s) => (
          <div key={s.num} className="story-card-editorial">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <span className="story-number">{s.num}</span>
              <span style={{
                fontSize: '0.7rem',
                fontWeight: 800,
                color: '#d4ff00',
                border: '1px solid rgba(212, 255, 0, 0.4)',
                padding: '0.2rem 0.6rem',
                borderRadius: '9999px',
                textTransform: 'uppercase'
              }}>
                {s.accent}
              </span>
            </div>

            <div style={{ marginTop: 'auto' }}>
              <h3 className="story-title">{s.title}</h3>
              <p className="story-desc">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
