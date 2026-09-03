import React, { useState } from 'react';
import { Plus, Check, ShoppingBag, Star } from 'lucide-react';
import { useStore } from '../../context/StoreContext';

export default function ProductCard({ product }) {
  const { addToCart } = useStore();
  const [isAdding, setIsAdding] = useState(false);
  const [justAdded, setJustAdded] = useState(false);

  const stock = product.STOCK_REMAINING ?? 0;
  const basePrice = parseFloat(product.BASE_PRICE || product.PRICE || 0);
  const sellingPrice = parseFloat(product.PRICE || basePrice || 0);
  const diff = sellingPrice - basePrice;
  const pct = basePrice > 0 ? ((diff / basePrice) * 100) : 0;
  const isSurged = diff > 0.05;

  const handleAdd = async (e) => {
    e.stopPropagation();
    if (stock <= 0 || isAdding) return;
    setIsAdding(true);
    try {
      await addToCart(product.id, product.PRODUCT_SIZE);
      setJustAdded(true);
      setTimeout(() => setJustAdded(false), 1500);
    } catch (err) {
      console.error(err);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <div className="nike-product-card">
      <div className="product-pedestal">
        <img 
          src={product.IMAGE || '/static/images/phone_flagship.svg'} 
          alt={product.PRODUCT_NAME} 
          className="pedestal-img"
          loading="lazy" 
        />

        {isSurged ? (
          <span className="badge-top-left volt" title={`Dynamic AI Surge (+${pct.toFixed(1)}%)`}>
            ⚡ +{pct.toFixed(0)}% AI Surge
          </span>
        ) : stock <= 0 ? (
          <span className="badge-top-left hot">0 Stock (Awaiting CEO Restock)</span>
        ) : stock <= 5 ? (
          <span className="badge-top-left hot">Only {stock} Left</span>
        ) : (
          <span className="badge-top-left normal">🔒 Base Floor</span>
        )}

        {/* Circular Floating Add Button */}
        <button 
          className="floating-quick-add"
          onClick={handleAdd}
          disabled={stock <= 0 || isAdding}
          title={stock <= 0 ? 'Out of Stock' : 'Add to Shopping Bag'}
        >
          {justAdded ? <Check size={18} style={{ color: '#10b981' }} /> : <Plus size={20} />}
        </button>
      </div>

      <div className="product-meta-block">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span className={`prod-kicker ${isSurged ? 'volt-text' : ''}`}>
            {isSurged ? 'Surge Dynamic' : product.PRODUCT_TYPE}
          </span>
          <span style={{ fontSize: '0.74rem', color: '#707072', display: 'flex', alignItems: 'center', gap: '3px' }}>
            <Star size={11} fill="#fa5400" color="#fa5400" />
            <strong style={{ color: '#111' }}>{product.RATING || '4.8'}</strong>
          </span>
        </div>

        <h4 className="prod-headline">{product.PRODUCT_NAME}</h4>
        <span className="prod-subtext">{product.PRODUCT_SIZE || 'Standard Edition'} • 0% Tax</span>

        <div className="prod-price-line">
          <span className="mrp-label">MRP :</span>
          <span>₹{sellingPrice.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}
