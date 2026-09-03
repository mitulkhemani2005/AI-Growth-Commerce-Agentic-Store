import React, { useState, useMemo } from 'react';
import { Search, X, SlidersHorizontal, PackageX } from 'lucide-react';
import { useStore } from '../../context/StoreContext';
import ProductCard from './ProductCard';

export default function ProductCatalog({ activeCategory, setActiveCategory }) {
  const { catalog } = useStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [inStockOnly, setInStockOnly] = useState(false);
  const [sortBy, setSortBy] = useState('featured');

  const filteredProducts = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    let prods = catalog.filter(p => {
      const matchCat = activeCategory === 'ALL' || (p.PRODUCT_TYPE || '').toLowerCase() === activeCategory.toLowerCase();
      const matchStock = !inStockOnly || (p.STOCK_REMAINING || 0) > 0;
      const matchQuery = !q || 
        (p.PRODUCT_NAME || '').toLowerCase().includes(q) ||
        (p.PRODUCT_TYPE || '').toLowerCase().includes(q) ||
        (p.PRODUCT_SIZE || '').toLowerCase().includes(q) ||
        (p.DESCRIPTION || '').toLowerCase().includes(q);

      return matchCat && matchStock && matchQuery;
    });

    if (sortBy === 'price-low') {
      prods.sort((a, b) => (parseFloat(a.PRICE) || 0) - (parseFloat(b.PRICE) || 0));
    } else if (sortBy === 'price-high') {
      prods.sort((a, b) => (parseFloat(b.PRICE) || 0) - (parseFloat(a.PRICE) || 0));
    } else if (sortBy === 'stock') {
      prods.sort((a, b) => (b.STOCK_REMAINING || 0) - (a.STOCK_REMAINING || 0));
    }

    return prods;
  }, [catalog, activeCategory, searchQuery, inStockOnly, sortBy]);

  return (
    <section className="catalog-container-full" id="catalog-grid-anchor">
      {/* Sticky Sub-Filter Bar */}
      <div className="sticky-subfilter-bar">
        <div className="subfilter-left">
          <h2 className="catalog-heading-title">
            {activeCategory === 'ALL' ? 'ALL PRODUCTS' : activeCategory.toUpperCase()} ({filteredProducts.length})
          </h2>
          {activeCategory !== 'ALL' && (
            <button 
              onClick={() => setActiveCategory('ALL')}
              style={{ fontSize: '0.78rem', color: '#707072', background: 'transparent', border: 'none', textDecoration: 'underline', cursor: 'pointer' }}
            >
              Clear Filter
            </button>
          )}
        </div>

        <div className="subfilter-right">
          {/* Search */}
          <div className="nike-search-bar" style={{ width: '220px' }}>
            <Search size={15} style={{ color: '#707072' }} />
            <input 
              type="text" 
              placeholder="Search devices..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery('')}
                style={{ background: 'transparent', border: 'none', color: '#707072', cursor: 'pointer' }}
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* In-Stock Filter */}
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer' }}>
            <input 
              type="checkbox" 
              checked={inStockOnly}
              onChange={(e) => setInStockOnly(e.target.checked)}
              style={{ accentColor: '#111' }}
            />
            <span>In-Stock Only</span>
          </label>

          {/* Sort Dropdown */}
          <select 
            className="filter-pill-toggle"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            style={{ outline: 'none' }}
          >
            <option value="featured">Sort By: Featured</option>
            <option value="price-low">Price: Low to High</option>
            <option value="price-high">Price: High to Low</option>
            <option value="stock">Highest Stock Velocity</option>
          </select>
        </div>
      </div>

      {/* Product Grid */}
      {filteredProducts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '5rem 1rem', color: '#707072' }}>
          <PackageX size={54} style={{ margin: '0 auto 1rem', opacity: 0.3 }} />
          <h4 style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', color: '#111', textTransform: 'uppercase' }}>
            No Matching Hardware Found
          </h4>
          <p style={{ fontSize: '0.9rem', marginTop: '0.4rem' }}>
            Try resetting your search query or choosing another category above.
          </p>
        </div>
      ) : (
        <div className="nike-products-grid">
          {filteredProducts.map((prod) => (
            <ProductCard key={prod.id} product={prod} />
          ))}
        </div>
      )}
    </section>
  );
}
