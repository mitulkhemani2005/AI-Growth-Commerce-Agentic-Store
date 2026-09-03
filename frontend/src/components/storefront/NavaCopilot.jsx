import React, { useState, useRef, useEffect } from 'react';
import { Sparkles, Send, X, Bot, Zap, PlusCircle, Check, CreditCard, ShieldCheck } from 'lucide-react';
import confetti from 'canvas-confetti';
import { api } from '../../api/client';
import { useStore } from '../../context/StoreContext';

const QUICK_CHIPS = [
  { label: '⚡ 1-Click AP2 Checkout', prompt: 'Checkout my cart now using AP2 tokenized protocol' },
  { label: '🎧 Recommended Cross-Sells', prompt: 'What high-margin accessories pair best with my cart?' },
  { label: '⚡ Dynamic Deals', prompt: 'Which hardware currently has the best dynamic pricing?' },
  { label: '💻 M3 Titanium Laptops', prompt: 'Show me premium titanium laptops with specs' },
  { label: '📦 Track My Orders', prompt: 'What is the real-time shipping status of my orders?' }
];

export default function NavaCopilot({ isOpen, setIsOpen }) {
  const { currentUser, refreshCart, refreshOrders, showToast } = useStore();
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hey **${currentUser.name.split(' ')[0]}**! I am **Nava**, your Autonomous AI Commerce Copilot.\n\nI can compare specs, recommend bundle cross-sells, check carrier tracking, or place instant 1-click orders using your **AP2 protocol mandate**.`
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

    // Direct conversational checkout detection
    const promptLower = prompt.toLowerCase();
    if (promptLower.includes('checkout') && (promptLower.includes('ap2') || promptLower.includes('cart') || promptLower.includes('now'))) {
      try {
        const checkoutRes = await api.conversationalCheckout({
          user_id: currentUser.id,
          payment_method: 'AP2',
          shipping_address: currentUser.address
        });

        if (checkoutRes.success) {
          try {
            confetti({ particleCount: 70, spread: 50, origin: { y: 0.7 } });
          } catch (e) {}

          setMessages(prev => [
            ...prev,
            {
              role: 'assistant',
              content: `🎉 **Order Confirmed via 1-Click AP2 Protocol!**\n\n- **Order ID**: \`${checkoutRes.order_id}\`\n- **Total Paid**: ₹${checkoutRes.total?.toFixed(2)} (0% Tax Free)\n- **Carrier Tracking**: \`${checkoutRes.tracking_number}\` (Bluedart Express)\n- **Status**: \`Confirmed\` (Stock automatically reserved)\n\nYour mandate was cryptographically validated with zero popup interruption!`
            }
          ]);
          await Promise.all([refreshCart(), refreshOrders()]);
          setIsTyping(false);
          return;
        }
      } catch (chkErr) {
        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: `⚠️ **Conversational Checkout Error:** ${chkErr.message}\n\nPlease verify that your bag is not empty and that total spend is within the ₹25,000 AP2 safety bound.`
          }
        ]);
        setIsTyping(false);
        return;
      }
    }

    try {
      const history = newMessages
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      const res = await api.chatWithNova(prompt, currentUser.id, history);

      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: res.response || res.message || 'I have processed your request.',
          toolCalls: res.tool_calls || []
        }
      ]);

      if (res.tool_calls && res.tool_calls.length > 0) {
        await Promise.all([refreshCart(), refreshOrders()]);
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `⚠️ **Error:** ${err.message}` }
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <>
      {/* Floating Athletic Capsule Button */}
      {!isOpen && (
        <button 
          className="floating-nova-capsule"
          onClick={() => setIsOpen(true)}
          title="Open Nava AI Copilot"
        >
          <Zap size={16} style={{ color: '#d4ff00' }} />
          <span style={{ fontWeight: 800, fontSize: '0.86rem', letterSpacing: '0.02em' }}>Ask Nava AI</span>
        </button>
      )}

      {/* Slide-Up Flyout Window */}
      {isOpen && (
        <div className="nova-flyout-window">
          {/* Header */}
          <div className="nova-window-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Zap size={16} style={{ color: '#d4ff00' }} />
              <h4>Nava AI Copilot</h4>
            </div>
            <button 
              onClick={() => setIsOpen(false)}
              style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer' }}
            >
              <X size={18} />
            </button>
          </div>

          {/* Chat Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem', background: '#fafafa' }} ref={scrollRef}>
            {messages.map((msg, idx) => {
              const isAssistant = msg.role === 'assistant';
              return (
                <div 
                  key={idx} 
                  style={{
                    alignSelf: isAssistant ? 'flex-start' : 'flex-end',
                    maxWidth: '85%',
                    background: isAssistant ? '#fff' : '#111',
                    color: isAssistant ? '#111' : '#fff',
                    padding: '0.75rem 1rem',
                    borderRadius: isAssistant ? '12px 12px 12px 2px' : '12px 12px 2px 12px',
                    border: isAssistant ? '1px solid #e5e5e5' : 'none',
                    fontSize: '0.82rem',
                    lineHeight: 1.5,
                    boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
                  }}
                >
                  <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>

                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div style={{ marginTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                      {msg.toolCalls.map((t, tIdx) => (
                        <span 
                          key={tIdx} 
                          style={{
                            fontSize: '0.7rem',
                            background: '#f0fdf4',
                            border: '1px solid #bbf7d0',
                            color: '#15803d',
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                            fontWeight: 700
                          }}
                        >
                          ✓ Executed Tool: {t.name || t.function_name}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {isTyping && (
              <div style={{ alignSelf: 'flex-start', background: '#fff', border: '1px solid #e5e5e5', borderRadius: '8px', padding: '0.5rem 0.85rem', fontSize: '0.78rem', color: '#707072' }}>
                Nava is analyzing hardware catalog & AP2 mandates...
              </div>
            )}
          </div>

          {/* Quick Chips */}
          <div style={{ padding: '0.5rem 0.85rem', background: '#fff', borderTop: '1px solid #e5e5e5', display: 'flex', gap: '0.4rem', overflowX: 'auto' }}>
            {QUICK_CHIPS.map((chip, idx) => (
              <button 
                key={idx}
                onClick={() => handleSend(chip.prompt)}
                style={{
                  whiteSpace: 'nowrap',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  background: '#f5f5f5',
                  border: '1px solid #e5e5e5',
                  borderRadius: '9999px',
                  padding: '0.3rem 0.65rem',
                  cursor: 'pointer'
                }}
              >
                {chip.label}
              </button>
            ))}
          </div>

          {/* Input Form */}
          <form 
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            style={{ padding: '0.75rem', background: '#fff', borderTop: '1px solid #e5e5e5', display: 'flex', gap: '0.5rem' }}
          >
            <input 
              type="text" 
              placeholder="Ask Nava or type 'Checkout with AP2'..."
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              style={{
                flex: 1,
                background: '#f5f5f5',
                border: '1px solid #e5e5e5',
                borderRadius: '9999px',
                padding: '0.5rem 1rem',
                fontSize: '0.82rem',
                outline: 'none'
              }}
            />
            <button 
              type="submit"
              disabled={!inputVal.trim() || isTyping}
              style={{
                background: '#111',
                color: '#fff',
                border: 'none',
                borderRadius: '50%',
                width: '36px',
                height: '36px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer'
              }}
            >
              <Send size={14} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
