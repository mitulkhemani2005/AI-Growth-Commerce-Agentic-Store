import React, { useState } from 'react';
import { ArrowUpRight, ArrowRight, IndianRupee, ShoppingBag, Package, Activity, Play, RefreshCw } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import ActivityPanel from './ActivityPanel';
import RuntimePanel from './RuntimePanel';
const money = value => new Intl.NumberFormat('en-IN', {style:'currency',currency:'INR',maximumFractionDigits:0}).format(value || 0);
export default function OverviewTab() {
  const { overview, treasury, agentsStatus, setActiveTab, triggerAllAgents, isScanningFleet, loadAllAdminData, runtime, connectionError } = useAdmin();
  const { showToast } = useStore();
  const [refreshing, setRefreshing] = useState(false);
  const kpis = overview?.kpis || {};
  const cycleCount = Object.values(agentsStatus?.agents || {}).reduce((sum, agent) => sum + agent.actions_count, 0);
  async function scan() { try { await triggerAllAgents(); showToast('Fleet cycles queued. Follow progress in the activity stream.'); } catch (error) { showToast(error.message, 'error'); } }
  return <div className="overview-page">
    <div className="ops-heading"><div><span className="eyebrow">OVERVIEW</span><h1>Your store, in motion<span>.</span></h1><p>Everything you need to see. Every agent working together.</p></div><div className="heading-actions"><button className="button button-quiet" disabled={refreshing} onClick={async () => {setRefreshing(true); await loadAllAdminData(); setRefreshing(false);}}><RefreshCw size={15} />Refresh</button><button className="button button-dark" disabled={isScanningFleet} onClick={scan}><Play size={14} />{isScanningFleet ? 'Queuing…' : 'Run fleet cycle'}</button></div></div>
    {connectionError && <div className="inline-error" role="alert">Connection interrupted: {connectionError}</div>}
    <div className="ops-system-line"><span className={`status-pill ${runtime?.background_agents_enabled ? 'success' : 'warning'}`}><i />{!runtime ? 'Connecting to agents…' : runtime.background_agents_enabled ? 'Autonomous fleet running' : 'Fleet stopped'}</span><span>{!runtime ? 'Checking GPU residency…' : runtime.gpu?.gpu_resident ? `${runtime.gpu.model} · 100% GPU` : 'GPU readiness required'}</span><span>Payments: {runtime?.payment_mode || 'connecting'}</span></div>
    <div className="metric-grid">{[{label:'Store balance',value:money(treasury?.bank_balance),note:'Available treasury',icon:IndianRupee},{label:'Total orders',value:kpis.total_orders ?? '—',note:`${kpis.active_orders || 0} in progress`,icon:ShoppingBag},{label:'Products to watch',value:kpis.low_stock_count ?? '—',note:'Low stock or sold out',icon:Package},{label:'Agent cycles',value:cycleCount,note:'Completed this session',icon:Activity}].map(({label,value,note,icon:Icon}) => <article className="metric-card" key={label}><div><span>{label}</span><Icon size={17} /></div><strong>{value}</strong><p>{note}</p></article>)}</div>
    <div className="ops-main-grid"><ActivityPanel /><div className="ops-right-column"><RuntimePanel /><section className="panel quick-links"><span className="eyebrow">KEEP THINGS MOVING</span><button onClick={() => setActiveTab('inventory')}><span><Package size={17} />Manage inventory</span><ArrowUpRight size={15} /></button><button onClick={() => setActiveTab('orders')}><span><ShoppingBag size={17} />Review orders</span><ArrowUpRight size={15} /></button><button onClick={() => setActiveTab('agents')}><span><Activity size={17} />See all agents</span><ArrowRight size={15} /></button></section></div></div>
  </div>;
}
