import React from 'react';

export default function MessageText({ text }) {
  return <span style={{whiteSpace:'pre-wrap'}}>{String(text || '').split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => part.startsWith('**') ? <strong key={index}>{part.slice(2,-2)}</strong> : part.startsWith('`') ? <code key={index}>{part.slice(1,-1)}</code> : part)}</span>;
}
