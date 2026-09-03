import React, { useState, useRef, useEffect } from 'react';
import { Crown, Send, Zap, Sparkles, CheckCircle2, RotateCcw, Wrench } from 'lucide-react';
import { api } from '../../api/client';
import { useAdmin } from '../../context/AdminContext';
import { useStore } from '../../context/StoreContext';

const ADMIN_CHIPS = [
  { label: '👔 CEO Briefing', prompt: 'CEO, provide an executive strategic briefing on store health and team alignment.' },
  { label: '🏷️ Discount Mobiles 10%', prompt: 'Price manager, discount Mobiles by 10% while strictly enforcing the BASE_PRICE floor.' },
  { label: '📦 Restock Low Stock', prompt: 'Inventory manager, audit warehouse and restock all low inventory items.' },
  { label: '🚚 Dispatch Logistics', prompt: 'Dispatcher, assign carrier tracking numbers and dispatch all confirmed orders.' },
  { label: '💰 Audit Financials', prompt: 'Finance manager, audit revenue, GMV, profit margins, and refund rate.' },
  { label: '⭐ Sentiment Analysis', prompt: 'Review manager, analyze customer sentiment and summarize reviews.' }
];

const INITIAL_MESSAGE = {
  role: 'assistant',
  content: `Welcome, Store Owner! I am your **Omnipotent AI Executive Command Agent**.\n\nI hold direct executive authority over all 7 autonomous specialist agents, databases, and closed-loop treasury.\n\nYou can issue direct strategic directives in natural language to any agent:\n- 👔 **CEO**: *"CEO, give me a strategic briefing and team alignment report"*\n- 🏷️ **Price Manager**: *"Discount Mobiles by 10% keeping base floor"*\n- 📦 **Inventory Manager**: *"Restock 20 units of NOVA ZenBook"*\n- 💰 **Finance Manager**: *"Audit store revenue and refund liability"*`,
  timestamp: new Date().toLocaleTimeString()
};

export default function CEOChatTab() {
  const { loadAllAdminData } = useAdmin();
  const { refreshCatalog, refreshOrders } = useStore();

  const [messages, setMessages] = useState([INITIAL_MESSAGE]);
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleClearChat = () => {
    setMessages([INITIAL_MESSAGE]);
  };

  const handleSend = async (promptToSend = inputVal) => {
    const prompt = promptToSend.trim();
    if (!prompt || isTyping) return;

    setInputVal('');
    const userMsg = {
      role: 'user',
      content: prompt,
      timestamp: new Date().toLocaleTimeString()
    };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setIsTyping(true);

    try {
      const history = newMessages
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      const res = await api.adminChat(prompt, history);

      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: res.response || res.message || 'Directive processed successfully.',
          toolCalls: res.tool_calls || res.tools_executed || [],
          timestamp: new Date().toLocaleTimeString()
        }
      ]);

      // Sync backend state
      await Promise.all([loadAllAdminData(), refreshCatalog(), refreshOrders()]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { 
          role: 'assistant', 
          content: `⚠️ **Command Execution Error:** ${err.message}`,
          timestamp: new Date().toLocaleTimeString()
        }
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: 'calc(100vh - 180px)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
            👑 Omnipotent Store Owner AI Command Center
          </h2>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
            Direct Natural Language & Multi-Agent Executive Command over all 7 specialist agents, databases & treasury.
          </p>
        </div>

        <button 
          className="action-btn"
          style={{ fontSize: '0.74rem' }}
          onClick={handleClearChat}
          title="Reset conversation"
        >
          <RotateCcw size={12} />
          <span>Clear Console</span>
        </button>
      </div>

      <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }} ref={scrollRef}>
          {messages.map((msg, idx) => {
            const isAgent = msg.role === 'assistant';
            return (
              <div key={idx} className={`chat-bubble ${isAgent ? 'copilot' : 'user'}`} style={{ maxWidth: '85%' }}>
                <div className={`bubble-avatar ${isAgent ? 'copilot' : 'user'}`}>
                  {isAgent ? <Crown size={15} style={{ color: '#f59e0b' }} /> : '👑'}
                </div>
                <div className="bubble-content">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem', gap: '1rem' }}>
                    <strong style={{ fontSize: '0.74rem', color: isAgent ? '#fbbf24' : '#c084fc', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      {isAgent ? 'Omnipotent CEO Command Agent' : 'Store Owner Direct Directive'}
                    </strong>
                    {msg.timestamp && (
                      <span style={{ fontSize: '0.68rem', color: '#64748b', fontFamily: 'monospace' }}>
                        {msg.timestamp}
                      </span>
                    )}
                  </div>

                  <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
                    {msg.content}
                  </div>

                  {/* Tool execution badges */}
                  {Array.isArray(msg.toolCalls) && msg.toolCalls.length > 0 && (
                    <div style={{ marginTop: '0.75rem', paddingTop: '0.5rem', borderTop: '1px solid rgba(255, 255, 255, 0.08)', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      <span style={{ fontSize: '0.68rem', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.03em' }}>
                        Executed Multi-Agent System Tools:
                      </span>
                      {msg.toolCalls.map((tc, tIdx) => (
                        <div key={tIdx} style={{
                          fontSize: '0.72rem',
                          fontFamily: 'monospace',
                          background: 'rgba(16, 185, 129, 0.1)',
                          border: '1px solid rgba(16, 185, 129, 0.25)',
                          color: '#34d399',
                          padding: '0.25rem 0.55rem',
                          borderRadius: '4px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px'
                        }}>
                          <Wrench size={11} />
                          <span>{typeof tc === 'string' ? tc : `${tc.tool || tc.name || 'Tool'} ✓`}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {isTyping && (
            <div className="chat-bubble copilot">
              <div className="bubble-avatar copilot">
                <Crown size={15} style={{ color: '#f59e0b' }} />
              </div>
              <div className="bubble-content" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="pulse-dot" style={{ width: '8px', height: '8px' }}></span>
                <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>CEO Agent is coordinating with specialist fleet & validating invariants...</span>
              </div>
            </div>
          )}
        </div>

        {/* Quick Suggestion Chips */}
        <div style={{ padding: '0.65rem 1.25rem', background: 'rgba(8, 12, 21, 0.65)', borderTop: '1px solid rgba(255, 255, 255, 0.06)', display: 'flex', gap: '0.5rem', overflowX: 'auto' }}>
          {ADMIN_CHIPS.map((chip, idx) => (
            <button 
              key={idx} 
              className="quick-chip-btn"
              onClick={() => handleSend(chip.prompt)}
              disabled={isTyping}
            >
              <Zap size={11} />
              <span>{chip.label}</span>
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <form 
          className="copilot-input-row"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <input 
            type="text"
            className="chat-text-input"
            placeholder="Give a strategic order to any specialist AI agent or database..."
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
          />
          <button 
            type="submit" 
            className="chat-send-btn"
            disabled={!inputVal.trim() || isTyping}
            title="Send Directive"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}

