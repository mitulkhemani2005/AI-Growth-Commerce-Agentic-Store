import React, { useState } from 'react';
import { Cpu, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';
import { api } from '../../api/client';
export default function RuntimePanel() {
  const { runtime, fetchTelemetry } = useAdmin();
  const { showToast } = useStore();
  const [retrying, setRetrying] = useState(false);
  const gpu = runtime?.gpu;
  async function retry() {
    setRetrying(true);
    try { const result = await api.retryRuntime(); await fetchTelemetry(); showToast(result.success ? 'Model verified on GPU. Agents are running.' : result.runtime_error, result.success ? 'success' : 'error'); }
    catch (error) { showToast(error.message, 'error'); }
    finally { setRetrying(false); }
  }
  return <section className="runtime-panel panel"><div className="panel-heading"><h2><Cpu size={18} />Local intelligence</h2><span className={`status-pill ${gpu?.gpu_resident ? 'success' : 'warning'}`}>{gpu?.gpu_resident ? '100% GPU' : 'Check runtime'}</span></div><div className="runtime-model"><span className="model-icon"><Cpu size={26} /></span><div><strong>{gpu?.model || 'Connecting to Ollama…'}</strong><p>{gpu?.gpu_resident ? 'Model weights fully resident in VRAM' : runtime?.runtime_error || 'Checking model residency'}</p></div></div><div className="runtime-meter"><span style={{width:`${gpu?.gpu_percent || 0}%`}} /></div><dl><div><dt>GPU model memory</dt><dd>{gpu?.vram_bytes ? `${(gpu.vram_bytes / 1048576).toFixed(0)} MiB` : '—'}</dd></div><div><dt>Agent fleet</dt><dd>{!runtime ? 'Connecting…' : runtime.background_agents_enabled ? 'Running' : 'Stopped'}</dd></div><div><dt>Completed AI requests</dt><dd>{gpu?.inference?.completed ?? '—'}</dd></div><div><dt>Inference</dt><dd>{gpu?.inference?.active ? 'Generating' : 'Ready for requests'}</dd></div></dl>{gpu?.inference?.last_error && <p className="inline-error">{gpu.inference.last_error}</p>}{runtime && !gpu?.gpu_resident && <button className="button button-dark" onClick={retry} disabled={retrying}><RefreshCw size={15} />{retrying ? 'Loading on GPU…' : 'Load model on GPU'}</button>}<p className="runtime-footnote">{gpu?.gpu_resident ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}CPU model fallback is blocked.</p></section>;
}
