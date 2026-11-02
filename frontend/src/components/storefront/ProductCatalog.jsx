import React, { useMemo, useState } from 'react';
import { Search, SlidersHorizontal, PackageSearch } from 'lucide-react';
import { useStore } from '../../context/StoreContext';
import ProductCard from './ProductCard';

export default function ProductCatalog({ activeCategory, setActiveCategory }) {
  const { catalog, isLoadingCatalog, catalogError, refreshCatalog } = useStore();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('featured');
  const [inStock, setInStock] = useState(false);
  const products = useMemo(() => {
    const items = catalog.filter(p => (activeCategory === 'ALL' || p.PRODUCT_TYPE === activeCategory) && (!inStock || p.STOCK_REMAINING > 0) && `${p.PRODUCT_NAME} ${p.PRODUCT_TYPE} ${p.DESCRIPTION} ${p.PRODUCT_SIZE}`.toLowerCase().includes(query.toLowerCase().trim()));
    if (sort !== 'featured') items.sort((a, b) => sort === 'low' ? a.PRICE - b.PRICE : b.PRICE - a.PRICE);
    return items;
  }, [catalog, activeCategory, inStock, query, sort]);
  return <section className="catalog-section page-width" id="catalog-grid-anchor">
    <div className="section-heading"><div><span className="eyebrow">THE COLLECTION</span><h2>Find your next upgrade.</h2></div><p>Good design. Useful technology.<br />Nothing you don’t need.</p></div>
    <div className="catalog-controls"><div className="category-tabs" aria-label="Product categories">{['ALL', 'Mobiles', 'Laptops', 'Audio', 'Accessories'].map(category => <button key={category} className={activeCategory === category ? 'active' : ''} onClick={() => setActiveCategory(category)}>{category === 'ALL' ? 'All products' : category}</button>)}</div><label className="search-field"><Search size={17} /><input aria-label="Search products" placeholder="Find something great…" value={query} onChange={event => setQuery(event.target.value)} /></label></div>
    <div className="catalog-meta"><span>{products.length} considered essentials</span><div><label><input type="checkbox" checked={inStock} onChange={event => setInStock(event.target.checked)} />In stock</label><SlidersHorizontal size={14} /><select aria-label="Sort products" value={sort} onChange={event => setSort(event.target.value)}><option value="featured">Recommended</option><option value="low">Price: low to high</option><option value="high">Price: high to low</option></select></div></div>
    {catalogError ? <div className="empty-state" role="alert"><p>{catalogError}</p><button className="button button-dark" onClick={refreshCatalog}>Try again</button></div> : isLoadingCatalog ? <div className="loading-grid" role="status">{Array.from({ length: 4 }, (_, i) => <div className="skeleton" key={i} />)}<span className="sr-only">Loading products</span></div> : products.length ? <div className="products-grid">{products.map(product => <ProductCard key={product.id} product={product} />)}</div> : <div className="empty-state"><PackageSearch size={32} /><h3>No matches just yet.</h3><p>Try a different search or category.</p></div>}
  </section>;
}
