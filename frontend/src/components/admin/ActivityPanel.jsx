import React, { useState } from 'react';
import { Activity, Pause, Play, RefreshCw, ArrowUpRight } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';

export default function ActivityPanel({ expanded = false }) {
  const { agentLogs, fetchTelemetry, connectionError, lastSync, setActiveTab } = useAdmin();
  const [filter, setFilter] = useState('all');
  const [showMessages, setShowMessages] = useState(false);
  const [paused, setPaused] = useState(false);
  const [snapshot, setSnapshot] = useState([]);
  const logs = paused ? snapshot : agentLogs;
  const names = [...new Set(logs.map(log => log.agent_name))];
  const shown = logs.filter(log => (filter === 'all' || log.agent_name === filter) && (showMessages || !log.action?.includes('Message ->'))).slice(0, expanded ? 80 : 12);
  const pause = () => { if (!paused) setSnapshot(agentLogs); setPaused(!paused); };
  return <section className="activity-panel panel">
    <div className="panel-heading"><div><span className="eyebrow">HAPPENING NOW</span><h2><Activity size={19} />Recent agent activity</h2></div><span className={`status-pill ${connectionError ? 'error' : paused ? 'neutral' : 'success'}`}><i />{connectionError ? 'Disconnected' : paused ? 'Paused' : 'Live · 2s refresh'}</span></div>
    <div className="activity-toolbar"><select aria-label="Filter activity by agent" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All agents</option>{names.map(name => <option key={name}>{name}</option>)}</select><label className="activity-message-toggle"><input type="checkbox" checked={showMessages} onChange={event => setShowMessages(event.target.checked)} />Messages</label><span className="sync-time">{lastSync ? `Updated ${lastSync.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}` : 'Connecting…'}</span><button className="icon-button" onClick={pause} aria-label={paused ? 'Resume activity' : 'Pause activity'}>{paused ? <Play size={15} /> : <Pause size={15} />}</button><button className="icon-button" onClick={fetchTelemetry} aria-label="Refresh agent activity"><RefreshCw size={15} /></button></div>
    {connectionError && <div className="inline-error" role="alert">{connectionError}</div>}
    <div className="activity-list" aria-live={paused ? 'off' : 'polite'}>{shown.length ? shown.map(log => <article className="activity-event" key={log.id}><span className={`event-dot ${/fail|error|block/i.test(log.action) ? 'error' : ''}`} /><div><div className="event-title"><strong>{log.action}</strong><time dateTime={log.timestamp}>{new Date(log.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time></div><span className="event-agent">{log.agent_name}</span><p>{typeof log.details === 'object' ? JSON.stringify(log.details) : log.details}</p></div></article>) : <div className="empty-state"><Activity size={30} /><h3>Waiting for the next cycle</h3><p>Activity appears here as agents start, finish, or encounter an error. Check the runtime status if the fleet is stopped.</p></div>}</div>
    {!expanded && <button className="panel-footer-link" onClick={() => setActiveTab('activity')}>View the activity stream<ArrowUpRight size={15} /></button>}
  </section>;
}
