import { EventBus } from './events/EventBus';

interface AgentLog {
  id: string;
  agent_name: string;
  action: string;
  details: string;
  affected_items?: string[];
  timestamp: string;
}

interface AgentMessage {
  id?: string;
  message_id?: string;
  from_agent: string;
  to_agent: string;
  subject: string;
  payload?: any;
  timestamp: string;
}

const AGENT_MAP: Record<string, { slug: string; phaserId: string; room: string; emoji: string }> = {
  'CEO Agent': { slug: 'ceo', phaserId: 'agt_ceo', room: 'manager', emoji: '👑' },
  'ceo': { slug: 'ceo', phaserId: 'agt_ceo', room: 'manager', emoji: '👑' },
  'Price Manager Agent': { slug: 'price_manager', phaserId: 'agt_price', room: 'workspace', emoji: '🏷️' },
  'Price Manager': { slug: 'price_manager', phaserId: 'agt_price', room: 'workspace', emoji: '🏷️' },
  'price_manager': { slug: 'price_manager', phaserId: 'agt_price', room: 'workspace', emoji: '🏷️' },
  'Inventory Manager Agent': { slug: 'inventory_manager', phaserId: 'agt_inventory', room: 'datacenter', emoji: '📦' },
  'Inventory Manager': { slug: 'inventory_manager', phaserId: 'agt_inventory', room: 'datacenter', emoji: '📦' },
  'inventory_manager': { slug: 'inventory_manager', phaserId: 'agt_inventory', room: 'datacenter', emoji: '📦' },
  'Order Management Agent': { slug: 'order_manager', phaserId: 'agt_order', room: 'workspace', emoji: '📋' },
  'Order Manager': { slug: 'order_manager', phaserId: 'agt_order', room: 'workspace', emoji: '📋' },
  'order_manager': { slug: 'order_manager', phaserId: 'agt_order', room: 'workspace', emoji: '📋' },
  'Finance Manager Agent': { slug: 'finance_manager', phaserId: 'agt_finance', room: 'meeting', emoji: '💰' },
  'Finance Manager': { slug: 'finance_manager', phaserId: 'agt_finance', room: 'meeting', emoji: '💰' },
  'finance_manager': { slug: 'finance_manager', phaserId: 'agt_finance', room: 'meeting', emoji: '💰' },
  'Dispatcher Agent': { slug: 'dispatcher', phaserId: 'agt_dispatcher', room: 'showroom', emoji: '🚚' },
  'Dispatcher': { slug: 'dispatcher', phaserId: 'agt_dispatcher', room: 'showroom', emoji: '🚚' },
  'dispatcher': { slug: 'dispatcher', phaserId: 'agt_dispatcher', room: 'showroom', emoji: '🚚' },
  'Review and Feedback Manager': { slug: 'review_manager', phaserId: 'agt_review', room: 'meeting', emoji: '⭐' },
  'Review Manager': { slug: 'review_manager', phaserId: 'agt_review', room: 'meeting', emoji: '⭐' },
  'review_manager': { slug: 'review_manager', phaserId: 'agt_review', room: 'meeting', emoji: '⭐' },
};

function resolveAgent(name: string) {
  if (!name) return null;
  if (AGENT_MAP[name]) return AGENT_MAP[name];
  const lower = name.toLowerCase();
  for (const [k, v] of Object.entries(AGENT_MAP)) {
    if (lower.includes(k.toLowerCase()) || k.toLowerCase().includes(lower)) {
      return v;
    }
  }
  return null;
}

class LiveStoreBridge {
  private timer: any = null;
  private seenLogIds = new Set<string>();
  private seenMsgIds = new Set<string>();
  private isInitialized = false;

  public start() {
    if (this.timer) return;
    this.poll();
    this.timer = setInterval(() => this.poll(), 2500);
  }

  public stop() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private async poll() {
    try {
      await Promise.all([this.fetchLogs(), this.fetchMessages()]);
      this.isInitialized = true;
    } catch (e) {
      // Backend might be offline or still starting
    }
  }

  private async fetchLogs() {
    try {
      const res = await fetch('/api/admin/agent-logs?limit=15');
      if (!res.ok) return;
      const data = await res.json();
      const logs: AgentLog[] = data.logs || [];

      // If first run, populate seen list so we don't trigger 15 notifications at once
      if (!this.isInitialized) {
        logs.forEach((l) => this.seenLogIds.add(l.id));
        return;
      }

      // Process new logs chronologically (reverse of descending)
      const newLogs = logs.filter((l) => !this.seenLogIds.has(l.id)).reverse();
      for (const log of newLogs) {
        this.seenLogIds.add(log.id);
        this.handleLogEvent(log);
      }
    } catch (e) {
      // ignore
    }
  }

  private async fetchMessages() {
    try {
      const res = await fetch('/api/admin/agent-messages?limit=10');
      if (!res.ok) return;
      const data = await res.json();
      const messages: AgentMessage[] = data.messages || [];

      if (!this.isInitialized) {
        messages.forEach((m) => this.seenMsgIds.add(m.message_id || m.id || `${m.from_agent}-${m.timestamp}`));
        return;
      }

      const newMsgs = messages.filter((m) => {
        const id = m.message_id || m.id || `${m.from_agent}-${m.timestamp}`;
        return !this.seenMsgIds.has(id);
      }).reverse();

      for (const msg of newMsgs) {
        const id = msg.message_id || msg.id || `${msg.from_agent}-${msg.timestamp}`;
        this.seenMsgIds.add(id);
        this.handleMessageEvent(msg);
      }
    } catch (e) {
      // ignore
    }
  }

  private handleLogEvent(log: AgentLog) {
    const meta = resolveAgent(log.agent_name);
    if (!meta) return;

    // 1. Move agent to their designated department room
    EventBus.emit('chat:agent-move', { agentId: meta.phaserId, roomId: meta.room });

    // 2. Set working status (walks to desk, types particles)
    EventBus.emit('agent:status', { agentId: meta.phaserId, status: 'working' });

    // 3. Render animated dialogue bubble
    let text = `${meta.emoji} ${log.action}`;
    if (log.details) {
      const cleanDetails = log.details.slice(0, 45).replace(/\n/g, ' ');
      text += `: ${cleanDetails}${log.details.length > 45 ? '...' : ''}`;
    }
    EventBus.emit('chat:agent-bubble', { agentSlug: meta.slug, text, duration: 4000 });

    // 4. Return to idle after 4.5 seconds
    setTimeout(() => {
      EventBus.emit('agent:status', { agentId: meta.phaserId, status: 'idle' });
    }, 4500);
  }

  private handleMessageEvent(msg: AgentMessage) {
    const fromMeta = resolveAgent(msg.from_agent);
    const toMeta = resolveAgent(msg.to_agent);

    if (fromMeta) {
      // Gather in meeting room for cross-agent discussion if sending to another agent
      if (toMeta && toMeta.slug !== fromMeta.slug) {
        EventBus.emit('chat:agent-move', { agentId: fromMeta.phaserId, roomId: 'meeting' });
        EventBus.emit('chat:agent-move', { agentId: toMeta.phaserId, roomId: 'meeting' });
      }

      EventBus.emit('agent:status', { agentId: fromMeta.phaserId, status: 'working' });
      const snippet = msg.subject || (typeof msg.payload === 'string' ? msg.payload : 'Discussing store policy');
      const cleanSnippet = snippet.slice(0, 40);
      EventBus.emit('chat:agent-bubble', {
        agentSlug: fromMeta.slug,
        text: `💬 To @${toMeta?.slug || msg.to_agent}: ${cleanSnippet}`,
        duration: 3500,
      });

      setTimeout(() => {
        EventBus.emit('agent:status', { agentId: fromMeta.phaserId, status: 'idle' });
      }, 4000);
    }
  }
}

export const liveStoreBridge = new LiveStoreBridge();
