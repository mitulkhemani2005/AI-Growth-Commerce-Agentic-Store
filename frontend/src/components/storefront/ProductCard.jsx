import React, { useState } from 'react';
import { Plus, Check, Star } from 'lucide-react';
import { useStore } from '../../context/StoreContext';

export default function ProductCard({ product }) {
  const { addToCart } = useStore();
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const stock = Number(product.STOCK_REMAINING || 0);
  async function add() {
    if (adding || stock < 1) return;
    setAdding(true);
    try { await addToCart(product.id, product.PRODUCT_SIZE); setAdded(true); }
    catch { /* Store context displays the request error. */ }
    finally { setAdding(false); }
  }
  return <article className="product-card">
    <div className={`product-image tone-${product.PRODUCT_TYPE?.toLowerCase()}`}>
      <span className={`product-label ${stock === 0 ? 'sold-out' : ''}`}>{stock === 0 ? 'Restocking soon' : stock <= 5 ? `Only ${stock} left` : 'The Nova edit'}</span>
      <img src={product.IMAGE || '/static/images/phone_flagship.svg'} alt={product.PRODUCT_NAME} loading="lazy" />
      <button className={`product-add ${added ? 'added' : ''}`} onClick={add} disabled={adding || stock < 1} aria-label={`Add ${product.PRODUCT_NAME} to bag`}>{added ? <Check size={19} /> : <Plus size={20} />}</button>
    </div>
    <div className="product-category"><span>{product.PRODUCT_TYPE}</span><span className="rating"><Star size={12} fill="currentColor" />{Number(product.RATING || 4.5).toFixed(1)}</span></div>
    <h3>{product.PRODUCT_NAME.replace(/^NOVA\s+/i, '')}</h3><p>{product.PRODUCT_SIZE || 'Standard edition'}</p>
    <div className="product-price">{new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(product.PRICE)}<span>Free delivery</span></div>
  </article>;
}
