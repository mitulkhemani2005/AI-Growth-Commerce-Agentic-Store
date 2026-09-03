import React, { useState, useRef, useEffect } from 'react';
import { Crown, Send, Zap, Sparkles, CheckCircle2 } from 'lucide-react';
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

export default function CEOChatTab() {
  const { loadAllAdminData } = useAdmin();
  const { refreshCatalog, refreshOrders } = useStore();

  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Welcome, Store Owner! I am your **Omnipotent AI Executive Command Agent**.\n\nI hold direct executive authority over all 7 autonomous specialist agents, databases, and the Inter-Agent Message Bus.\n\nYou can issue direct strategic directives in natural language to any agent:\n- 👔 **CEO**: *"CEO, give me a strategic briefing and team alignment report"*\n- 🏷️ **Price Manager**: *"Discount Mobiles by 10% keeping base floor"*\n- 📦 **Inventory Manager**: *"Restock 20 units of NOVA ZenBook"*`
    }
  ]);
  const [inputVal, setInputVal] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleSend = async (promptToSend = inputVal) => {
    const prompt = promptToSend.trim();
    if (!prompt || isTyping) return;

    setInputVal('');
    const newMessages = [...messages, { role: 'user', content: prompt }];
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
          toolCalls: res.tool_calls || res.tools_executed || []
        }
      ]);

      // Sync backend state
      await Promise.all([loadAllAdminData(), refreshCatalog(), refreshOrders()]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `⚠️ **Command Execution Error:** ${err.message}` }
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', height: 'calc(100vh - 180px)' }}>
      <div>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>
          Omnipotent Store Owner AI Command Center
        </h2>
        <p style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
          Direct Natural Language & Multi-Agent Executive Command over all 7 specialist agents, databases & treasury.
        </p>
      </div>

      <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }} ref={scrollRef}>
          {messages.map((msg, idx) => {
            const isAgent = msg.role === 'assistant';
            return (
              <div key={idx} className={`chat-bubble ${isAgent ? 'copilot' : 'user'}`} style={{ maxWidth: '85%' }}>
                <div className={`bubble-avatar ${isAgent ? 'copilot' : 'user'}`}>
                  {isAgent ? <Crown size={14} style={{ color: '#f59e0b' }} /> : '👑'}
                </div>
                <div className="bubble-content">
                  <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                    {msg.content}
                  </div>
                </div>
              </div>
            );
          })}

          {isTyping && (
            <div className="chat-bubble copilot">
              <div className="bubble-avatar copilot">
                <Crown size={14} style={{ color: '#f59e0b' }} />
              </div>
              <div className="bubble-content" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span className="pulse-dot" style={{ width: '6px', height: '6px' }}></span>
                <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>CEO Agent is coordinating with specialist fleet...</span>
              </div>
            </div>
          )}
        </div>

        {/* Chips */}
        <div style={{ padding: '0.5rem 1rem', background: 'rgba(8, 12, 21, 0.5)', borderTop: '1px solid rgba(255, 255, 255, 0.05)', display: 'flex', gap: '0.5rem', overflowX: 'auto' }}>
          {ADMIN_CHIPS.map((chip, idx) => (
            <button 
              key={idx} 
              className="quick-chip-btn"
              onClick={() => handleSend(chip.prompt)}
            >
              <Zap size={11} />
              <span>{chip.label}</span>
            </button>
          ))}
        </div>

        {/* Input */}
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
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
