import { EventBus } from './events/EventBus';

export interface AgentLog {
  id: string;
  agent_name: string;
  action: string;
  details: string;
  affected_items?: string[];
  timestamp: string;
}

export interface AgentMessage {
  id?: string;
  message_id?: string;
  from?: string;
  to?: string;
  from_agent?: string;
  to_agent?: string;
  subject: string;
  event_type?: string;
  payload?: any;
  priority?: string;
  timestamp: string;
}

export interface ResolvedAgent {
  slug: string;
  name: string;
  phaserId: string;
  room: string;
  emoji: string;
  deskPos: { x: number; y: number };
  role: string;
}

export const AGENT_REGISTRY_MAP: Record<string, ResolvedAgent> = {
  'ceo': {
    slug: 'ceo',
    name: 'CEO Agent',
    phaserId: 'agt_ceo',
    room: 'manager',
    emoji: '👑',
    deskPos: { x: 840, y: 150 },
    role: 'Fleet Commander & Store Strategist',
  },
  'price_manager': {
    slug: 'price_manager',
    name: 'Price Manager',
    phaserId: 'agt_price',
    room: 'workspace',
    emoji: '🏷️',
    deskPos: { x: 760, y: 380 },
    role: 'Head of Dynamic Pricing & Margins',
  },
  'order_manager': {
    slug: 'order_manager',
    name: 'Order Manager',
    phaserId: 'agt_order',
    room: 'workspace',
    emoji: '📋',
    deskPos: { x: 940, y: 380 },
    role: 'Order Lifecycle & SLA Governance',
  },
  'inventory_manager': {
    slug: 'inventory_manager',
    name: 'Inventory Manager',
    phaserId: 'agt_inventory',
    room: 'datacenter',
    emoji: '📦',
    deskPos: { x: 850, y: 640 },
    role: 'Warehouse Logistics & Restocking',
  },
  'finance_manager': {
    slug: 'finance_manager',
    name: 'Finance Manager',
    phaserId: 'agt_finance',
    room: 'meeting',
    emoji: '💰',
    deskPos: { x: 365, y: 620 },
    role: 'Chief Financial Officer & Treasury',
  },
  'dispatcher': {
    slug: 'dispatcher',
    name: 'Dispatcher Agent',
    phaserId: 'agt_dispatcher',
    room: 'showroom',
    emoji: '🚚',
    deskPos: { x: 360, y: 230 },
    role: 'Express Fulfillment & Intent Router',
  },
  'review_manager': {
    slug: 'review_manager',
    name: 'Review Manager',
    phaserId: 'agt_review',
    room: 'meeting',
    emoji: '⭐',
    deskPos: { x: 465, y: 620 },
    role: 'Customer Sentiment & Reviews Lead',
  },
};

export function resolveAgent(nameOrSlug?: string): ResolvedAgent | null {
  if (!nameOrSlug) return null;
  const raw = nameOrSlug.trim();
  const lower = raw.toLowerCase();

  // Exact key match
  if (AGENT_REGISTRY_MAP[raw]) return AGENT_REGISTRY_MAP[raw];
  if (AGENT_REGISTRY_MAP[lower]) return AGENT_REGISTRY_MAP[lower];

  // Slug aliases
  if (lower.includes('ceo')) return AGENT_REGISTRY_MAP['ceo'];
  if (lower.includes('price')) return AGENT_REGISTRY_MAP['price_manager'];
  if (lower.includes('order')) return AGENT_REGISTRY_MAP['order_manager'];
  if (lower.includes('inventory') || lower.includes('stock')) return AGENT_REGISTRY_MAP['inventory_manager'];
  if (lower.includes('finance') || lower.includes('cfo')) return AGENT_REGISTRY_MAP['finance_manager'];
  if (lower.includes('dispatch')) return AGENT_REGISTRY_MAP['dispatcher'];
  if (lower.includes('review') || lower.includes('sentiment') || lower.includes('feedback')) {
    return AGENT_REGISTRY_MAP['review_manager'];
  }

  return null;
}

function formatPayloadSummary(payload: any): string {
  if (!payload) return '';
  if (typeof payload === 'string') return payload;

  if (payload.action && payload.details) {
    return `${payload.action}: ${payload.details}`;
  }
  if (payload.reason) {
    return `${payload.reason}`;
  }
  if (payload.adjustments && Array.isArray(payload.adjustments)) {
    const list = payload.adjustments.slice(0, 3).map((a: any) => `${a.product_id || a.name || 'Item'}: ₹${a.new_price || a.price || ''}`).join(', ');
    return `Updated pricing: ${list}`;
  }
  if (payload.status_breakdown) {
    const b = payload.status_breakdown;
    return `Orders: ${Object.entries(b).map(([k, v]) => `${k}=${v}`).join(', ')}`;
  }
  if (payload.total_orders !== undefined) {
    return `Processed ${payload.total_orders} orders. Pipeline status active.`;
  }
  if (payload.refunds_processed !== undefined) {
    return `Processed ${payload.refunds_processed} refunds. Treasury balance verified.`;
  }

  try {
    const json = JSON.stringify(payload);
    return json.length > 90 ? `${json.slice(0, 87)}...` : json;
  } catch {
    return '';
  }
}

function generateCorporateReply(fromSlug: string, _toSlug: string, subject: string): string {
  const s = subject.toUpperCase();
  if (s.includes('PRICE') || s.includes('MARGIN')) {
    return 'Margin confirmed. Price strategy approved for store catalog.';
  }
  if (s.includes('RESTOCK') || s.includes('INVENTORY') || s.includes('STOCK')) {
    return 'Purchase order authorized. Warehouse dock notified for intake.';
  }
  if (s.includes('ORDER') || s.includes('DELIVERY') || s.includes('STATUS')) {
    return 'Order manifest verified. Tracking status updated in customer portal.';
  }
  if (s.includes('REFUND') || s.includes('FINANCE') || s.includes('TREASURY')) {
    return 'Treasury disbursement authorized under corporate SLA policy.';
  }
  if (s.includes('REVIEW') || s.includes('SENTIMENT') || s.includes('FEEDBACK')) {
    return 'Sentiment metrics acknowledged. Recommendations incorporated into roadmap.';
  }
  if (fromSlug === 'ceo') {
    return 'Directive acknowledged, Mr. CEO. Immediate execution underway.';
  }
  return 'Corporate communication acknowledged. Operational logs synchronized.';
}

class LiveStoreBridge {
  private timer: any = null;
  private seenLogIds = new Set<string>();
  private seenMsgIds = new Set<string>();
  private isInitialized = false;

  public start() {
    if (this.timer) return;
    this.poll();
    this.timer = setInterval(() => this.poll(), 2000);
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
    } catch {
      // Backend starting or reconnecting
    }
  }

  private async fetchLogs() {
    try {
      const res = await fetch('/api/admin/agent-logs?limit=15');
      if (!res.ok) return;
      const data = await res.json();
      const logs: AgentLog[] = data.logs || [];

      if (!this.isInitialized) {
        logs.forEach((l) => this.seenLogIds.add(l.id));
        return;
      }

      const newLogs = logs.filter((l) => !this.seenLogIds.has(l.id)).reverse();
      for (const log of newLogs) {
        this.seenLogIds.add(log.id);
        this.handleLogEvent(log);
      }
    } catch {
      // ignore
    }
  }

  private async fetchMessages() {
    try {
      const res = await fetch('/api/admin/agent-messages?limit=15');
      if (!res.ok) return;
      const data = await res.json();
      const messages: AgentMessage[] = data.messages || [];

      if (!this.isInitialized) {
        messages.forEach((m) => {
          const from = m.from_agent || m.from || 'Agent';
          const id = m.message_id || m.id || `${from}-${m.timestamp}`;
          this.seenMsgIds.add(id);
        });
        return;
      }

      const newMsgs = messages.filter((m) => {
        const from = m.from_agent || m.from || 'Agent';
        const id = m.message_id || m.id || `${from}-${m.timestamp}`;
        return !this.seenMsgIds.has(id);
      }).reverse();

      for (const msg of newMsgs) {
        const from = msg.from_agent || msg.from || 'Agent';
        const id = msg.message_id || msg.id || `${from}-${msg.timestamp}`;
        this.seenMsgIds.add(id);
        this.handleMessageEvent(msg);
      }
    } catch {
      // ignore
    }
  }


  private handleLogEvent(log: AgentLog) {
    const meta = resolveAgent(log.agent_name);
    if (!meta) return;

    // 1. Emit store log for Group Chat visibility
    EventBus.emit('store:agent-log', {
      id: log.id,
      agentSlug: meta.slug,
      agentName: meta.name,
      agentColor: meta.slug,
      action: log.action,
      details: log.details,
      timestamp: log.timestamp || new Date().toISOString(),
    });

    // 2. Set working status in office (types at desk)
    EventBus.emit('agent:status', { agentSlug: meta.slug, agentId: meta.phaserId, status: 'working' });

    // 3. Render animated dialogue bubble at desk
    let text = `${meta.emoji} ${log.action}`;
    if (log.details) {
      const clean = log.details.slice(0, 45).replace(/\n/g, ' ');
      text += `: ${clean}${log.details.length > 45 ? '...' : ''}`;
    }
    EventBus.emit('chat:agent-bubble', { agentSlug: meta.slug, text, duration: 4000 });

    // 4. Return to idle
    setTimeout(() => {
      EventBus.emit('agent:status', { agentSlug: meta.slug, agentId: meta.phaserId, status: 'idle' });
    }, 4500);
  }

  private handleMessageEvent(msg: AgentMessage) {
    const fromRaw = msg.from_agent || msg.from || '';
    const toRaw = msg.to_agent || msg.to || '';

    const fromMeta = resolveAgent(fromRaw) || {
      slug: 'dispatcher',
      name: fromRaw || 'Dispatcher Agent',
      phaserId: 'agt_dispatcher',
      room: 'showroom',
      emoji: '🏢',
      deskPos: { x: 360, y: 230 },
      role: 'Store Agent',
    };

    const isAll = toRaw.toUpperCase() === 'ALL' || toRaw.toUpperCase() === 'ALL_AGENTS' || toRaw === '';
    const toMeta = isAll ? null : resolveAgent(toRaw);

    const summary = formatPayloadSummary(msg.payload);
    const cleanSubject = (msg.subject || msg.event_type || 'Corporate Deliberation').replace(/_/g, ' ');
    const fullContent = summary ? `**${cleanSubject}**\n\n${summary}` : `**${cleanSubject}**`;
    const replyText = toMeta ? generateCorporateReply(fromMeta.slug, toMeta.slug, cleanSubject) : '';

    // 1. EMIT TO GROUP CHAT (ChatBox will display it immediately!)
    EventBus.emit('store:agent-message', {
      id: msg.id || msg.message_id || `msg-${Date.now()}`,
      fromSlug: fromMeta.slug,
      fromName: fromMeta.name,
      toSlug: toMeta ? toMeta.slug : 'all',
      toName: toMeta ? toMeta.name : 'All Store Fleet',
      subject: cleanSubject,
      content: fullContent,
      replyContent: replyText,
      payload: msg.payload,
      timestamp: msg.timestamp || new Date().toISOString(),
    });

    // 2. TRIGGER REALISTIC OFFICE INTERACTION
    if (isAll || fromMeta.slug === 'ceo' && cleanSubject.includes('FLEET')) {
      // Boardroom assembly meeting
      EventBus.emit('chat:boardroom-meeting', {
        leaderSlug: fromMeta.slug,
        leaderName: fromMeta.name,
        subject: cleanSubject,
        text: `${fromMeta.emoji} Boardroom Assembly: ${cleanSubject}`,
        duration: 6000,
      });
    } else if (toMeta && toMeta.slug !== fromMeta.slug) {
      // Direct desk visit & meeting ethics
      EventBus.emit('chat:agent-visit', {
        fromSlug: fromMeta.slug,
        fromName: fromMeta.name,
        fromDesk: fromMeta.deskPos,
        toSlug: toMeta.slug,
        toName: toMeta.name,
        toDesk: toMeta.deskPos,
        toRoom: toMeta.room,
        subject: cleanSubject,
        speakText: `${fromMeta.emoji} @${toMeta.name}: ${cleanSubject.slice(0, 32)}`,
        replyText: `${toMeta.emoji} @${fromMeta.name}: ${replyText.slice(0, 35)}`,
        duration: 5000,
      });
    } else {
      // Self desk action
      EventBus.emit('agent:status', { agentSlug: fromMeta.slug, agentId: fromMeta.phaserId, status: 'working' });
      EventBus.emit('chat:agent-bubble', {
        agentSlug: fromMeta.slug,
        text: `💬 ${cleanSubject}: ${summary.slice(0, 35)}`,
        duration: 3500,
      });
      setTimeout(() => {
        EventBus.emit('agent:status', { agentSlug: fromMeta.slug, agentId: fromMeta.phaserId, status: 'idle' });
      }, 4000);
    }
  }
}

export const liveStoreBridge = new LiveStoreBridge();
