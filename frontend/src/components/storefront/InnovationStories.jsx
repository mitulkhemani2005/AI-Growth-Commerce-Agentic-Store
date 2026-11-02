import React from 'react';
import { ArrowUpRight, Sparkles, PackageCheck, ShieldCheck } from 'lucide-react';
export default function InnovationStories({ onOpenNova }) {
  return <section className="intelligence-section page-width" id="innovation-stories-anchor">
    <div className="intelligence-intro"><span className="eyebrow">A LITTLE EXTRA INTELLIGENCE</span><h2>We take care of<br />the details.</h2><p>Behind every order is a team of specialist agents keeping things moving.</p><button className="button button-dark" onClick={onOpenNova}>Meet your copilot<ArrowUpRight size={16} /></button></div>
    <div className="intelligence-cards">{[{ icon: Sparkles, title: 'A personal point of view', text: 'Ask Nova to find products, compare specifications, or check your bag.' }, { icon: PackageCheck, title: 'Always in the loop', text: 'Inventory, orders, and dispatch stay connected through our live operations workspace.' }, { icon: ShieldCheck, title: 'Clear boundaries', text: 'Owner-set price floors and refund rules keep automated actions accountable.' }].map(({ icon: Icon, title, text }) => <article key={title}><Icon size={23} /><h3>{title}</h3><p>{text}</p></article>)}</div>
  </section>;
}
