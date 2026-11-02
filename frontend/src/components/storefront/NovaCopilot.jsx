import React, { useState, useRef, useEffect } from 'react';
import { Send, X, Zap } from 'lucide-react';
import confetti from 'canvas-confetti';
import { api } from '../../api/client';
import MessageText from '../shared/MessageText';
import { useStore } from '../../context/StoreContext';

const QUICK_CHIPS = [
  { label: '⚡ 1-Click AP2 Checkout', prompt: 'Checkout my cart now using AP2 tokenized protocol' },
  { label: '🎧 Find accessories', prompt: 'Recommend accessories that go with my cart' },
  { label: '⚡ Dynamic Deals', prompt: 'Which hardware currently has the best dynamic pricing?' },
  { label: '💻 M3 Titanium Laptops', prompt: 'Show me premium titanium laptops with specs' },
  { label: '📦 Track My Orders', prompt: 'What is the real-time shipping status of my orders?' }
];

export default function NovaCopilot({ isOpen, setIsOpen }) {
  const { currentUser, refreshCart, refreshOrders, setIsCartOpen } = useStore();
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `Hey **${currentUser.name.split(' ')[0]}**! I am **Nova**, your Autonomous AI Commerce Copilot.\n\nI can compare specs, recommend bundle cross-sells, check carrier tracking, or place instant 1-click orders using your **AP2 protocol mandate**.`
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
    if (promptLower.includes('checkout') && promptLower.includes('ap2')) {
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

      if (res.checkout_payload?.needs_razorpay_checkout) {
        setIsOpen(false);
        setIsCartOpen(true);
      }
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
          title="Open Nova AI Copilot"
        >
          <Zap size={16} style={{ color: '#d4ff00' }} />
          <span style={{ fontWeight: 800, fontSize: '0.86rem', letterSpacing: '0.02em' }}>Ask Nova AI</span>
        </button>
      )}

      {/* Slide-Up Flyout Window */}
      {isOpen && (
        <div className="nova-flyout-window">
          {/* Header */}
          <div className="nova-window-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Zap size={16} style={{ color: '#d4ff00' }} />
              <h4>Nova AI Copilot</h4>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              style={{ background: 'transparent', border: 'none', color: 'var(--text-primary)', cursor: 'pointer' }}
            >
              <X size={18} />
            </button>
          </div>

          {/* Chat Messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.85rem', background: 'var(--bg-surface)' }} ref={scrollRef}>
            {messages.map((msg, idx) => {
              const isAssistant = msg.role === 'assistant';
              return (
                <div
                  key={idx}
                  style={{
                    alignSelf: isAssistant ? 'flex-start' : 'flex-end',
                    maxWidth: '85%',
                    background: isAssistant ? 'var(--bg-glass-subtle)' : 'var(--bg-glass-subtle)',
                    color: isAssistant ? 'var(--text-primary)' : '#050811',
                    padding: '0.85rem 1.1rem',
                    borderRadius: isAssistant ? '14px 14px 14px 3px' : '14px 14px 3px 14px',
                    border: isAssistant ? '1px solid var(--border-glass)' : 'none',
                    fontSize: '0.84rem',
                    lineHeight: 1.55,
                    boxShadow: isAssistant ? 'none' : 'none'
                  }}
                >
                  <div><MessageText text={msg.content} /></div>

                  {msg.toolCalls && msg.toolCalls.length > 0 && (
                    <div style={{ marginTop: '0.6rem', display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                      {msg.toolCalls.map((t, tIdx) => (
                        <span
                          key={tIdx}
                          style={{
                            fontSize: '0.72rem',
                            background: 'rgba(16, 185, 129, 0.15)',
                            border: '1px solid rgba(16, 185, 129, 0.35)',
                            color: 'var(--neon-emerald)',
                            padding: '0.2rem 0.5rem',
                            borderRadius: '4px',
                            fontWeight: 700,
                            fontFamily: 'var(--font-mono)'
                          }}
                        >
                          ✓ {String(t.name || t.function_name || 'Updated').replaceAll('_', ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {isTyping && (
              <div style={{
                alignSelf: 'flex-start',
                background: 'var(--bg-glass-subtle)',
                border: '1px solid var(--border-glass)',
                padding: '0.65rem 1rem',
                borderRadius: '14px 14px 14px 3px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.78rem',
                color: 'var(--cyber-cyan)'
              }}>
                <span className="pulse-dot"></span>
                <span>Nova is checking your store…</span>
              </div>
            )}
          </div>

          {/* Quick Chip Suggestions */}
          <div style={{
            padding: '0.65rem 1rem',
            background: 'var(--bg-surface)',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            gap: '0.4rem',
            overflowX: 'auto',
            scrollbarWidth: 'none'
          }}>
            {QUICK_CHIPS.map((chip, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(chip.prompt)}
                disabled={isTyping}
                style={{
                  whiteSpace: 'nowrap',
                  fontSize: '0.74rem',
                  padding: '0.35rem 0.85rem',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: '9999px',
                  color: 'var(--text-secondary)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.18s ease'
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
            style={{ padding: '0.85rem 1rem', background: 'var(--bg-surface)', borderTop: '1px solid var(--border-subtle)', display: 'flex', gap: '0.6rem' }}
          >
            <input
              type="text"
              placeholder="Ask about a product or your order…"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              style={{
                flex: 1,
                background: 'rgba(255, 255, 255, 0.06)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '9999px',
                padding: '0.6rem 1.1rem',
                fontSize: '0.84rem',
                color: 'var(--text-bright)',
                outline: 'none'
              }}
            />
            <button
              type="submit"
              disabled={!inputVal.trim() || isTyping}
              style={{
                background: 'var(--cyber-cyan)',
                color: '#050811',
                border: 'none',
                borderRadius: '50%',
                width: '38px',
                height: '38px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                boxShadow: '0 0 14px var(--cyber-cyan-glow)'
              }}
            >
              <Send size={15} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
