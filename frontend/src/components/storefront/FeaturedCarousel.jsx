import React, { useRef } from 'react';
import { ChevronLeft, ChevronRight, ShoppingBag, Plus } from 'lucide-react';
import { useStore } from '../../context/StoreContext';

export default function FeaturedCarousel() {
  const { catalog, addToCart, showToast } = useStore();
  const trackRef = useRef(null);

  const scroll = (direction) => {
    if (trackRef.current) {
      const offset = direction === 'left' ? -380 : 380;
      trackRef.current.scrollBy({ left: offset, behavior: 'smooth' });
    }
  };

  // Select top featured items
  const featured = catalog.slice(0, 8);

  return (
    <section className="carousel-section">
      <div className="carousel-header-row">
        <div>
          <span style={{ fontSize: '0.8rem', fontWeight: 800, color: '#707072', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Curated Drops
          </span>
          <h3>Trending Hardware & Autonomous Picks</h3>
        </div>

        <div className="carousel-arrows">
          <button 
            className="arrow-circle-btn" 
            onClick={() => scroll('left')}
            title="Previous item"
          >
            <ChevronLeft size={20} />
          </button>
          <button 
            className="arrow-circle-btn" 
            onClick={() => scroll('right')}
            title="Next item"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      </div>

      <div className="carousel-snap-track" ref={trackRef}>
        {featured.map((prod) => {
          const stock = prod.STOCK_REMAINING ?? 0;
          const basePrice = parseFloat(prod.BASE_PRICE || prod.PRICE || 0);
          const sellingPrice = parseFloat(prod.PRICE || basePrice || 0);
          const diff = sellingPrice - basePrice;
          const isSurged = diff > 0.05;

          return (
            <div key={prod.id} className="carousel-item-card nike-product-card">
              <div className="product-pedestal">
                <img 
                  src={prod.IMAGE || '/static/images/phone_flagship.svg'} 
                  alt={prod.PRODUCT_NAME} 
                  className="pedestal-img"
                  loading="lazy"
                />

                {isSurged ? (
                  <span className="badge-top-left volt">⚡ AI Surged</span>
                ) : stock <= 0 ? (
                  <span className="badge-top-left hot">Restock Pending</span>
                ) : (
                  <span className="badge-top-left normal">Just In</span>
                )}

                <button 
                  className="floating-quick-add"
                  title="Add to Bag"
                  disabled={stock <= 0}
                  onClick={(e) => {
                    e.stopPropagation();
                    addToCart(prod.id, prod.PRODUCT_SIZE);
                  }}
                >
                  <Plus size={20} />
                </button>
              </div>

              <div className="product-meta-block">
                <span className={`prod-kicker ${isSurged ? 'volt-text' : ''}`}>
                  {isSurged ? 'Dynamic Surge Active' : prod.PRODUCT_TYPE}
                </span>
                <h4 className="prod-headline">{prod.PRODUCT_NAME}</h4>
                <span className="prod-subtext">{prod.PRODUCT_SIZE || 'Standard Edition'}</span>
                
                <div className="prod-price-line">
                  <span className="mrp-label">MRP :</span>
                  <span>₹{sellingPrice.toFixed(2)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
