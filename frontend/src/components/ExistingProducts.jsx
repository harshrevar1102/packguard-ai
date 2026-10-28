import React, { useState, useEffect } from 'react';
import { Search, Folder, Trash2, ArrowLeft, Calendar, FileText, AlertCircle } from 'lucide-react';

export default function ExistingProducts({ onNavigate, onSelectProduct }) {
  const [products, setProducts] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingProductId, setDeletingProductId] = useState(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  useEffect(() => {
    fetchProducts();
  }, []);

  const fetchProducts = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/products');
      if (!res.ok) throw new Error('Failed to fetch products');
      const data = await res.json();
      setProducts(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteClick = (e, product) => {
    e.stopPropagation();
    setDeletingProductId(product.id);
    setShowConfirmModal(true);
  };

  const confirmDelete = async () => {
    if (!deletingProductId) return;
    try {
      const res = await fetch(`/api/products/${deletingProductId}`, {
        method: 'DELETE'
      });
      if (!res.ok) throw new Error('Failed to delete product');
      setProducts(products.filter(p => p.id !== deletingProductId));
      setShowConfirmModal(false);
      setDeletingProductId(null);
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  };

  const filteredProducts = products.filter(p =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div>
      <div className="nav-breadcrumbs">
        <span className="back-link" onClick={() => onNavigate('home')}>
          <ArrowLeft size={16} /> Back to Options
        </span>
      </div>

      <div className="page-header">
        <div>
          <h2 className="page-title">Existing Products</h2>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Select a product to view previous analyses or start a new verification.
          </p>
        </div>

        <div className="search-bar-wrapper">
          <Search size={18} color="var(--color-text-dim)" />
          <input
            type="text"
            className="search-input"
            placeholder="Search products by name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)' }}>
          Loading products...
        </div>
      ) : error ? (
        <div className="conflict-alert">
          <h4><AlertCircle size={18} /> Error</h4>
          <p>{error}</p>
        </div>
      ) : filteredProducts.length === 0 ? (
        <div className="empty-state">
          <Folder size={48} className="empty-state-icon" />
          {searchQuery ? (
            <>
              <h3>No matching products found</h3>
              <p>No products match your search query "{searchQuery}".</p>
            </>
          ) : (
            <>
              <h3>No products saved yet</h3>
              <p>The product catalog is currently empty. Run a new analysis to create and save your first product.</p>
              <button 
                className="btn-primary" 
                style={{ width: 'auto', marginTop: '1.25rem' }}
                onClick={() => onNavigate('new')}
              >
                Analyse New Product
              </button>
            </>
          )}
        </div>
      ) : (
        <div className="products-grid">
          {filteredProducts.map((p) => (
            <div
              key={p.id}
              className="product-card"
              onClick={() => onSelectProduct(p.id)}
            >
              <div>
                <div className="product-card-top">
                  <h4 className="product-card-title">{p.name}</h4>
                  <button
                    className="delete-icon-btn"
                    title="Delete product and data"
                    onClick={(e) => handleDeleteClick(e, p)}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              <div className="product-meta-row">
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <FileText size={14} />
                  {p.analysis_ids ? p.analysis_ids.length : 0} {p.analysis_ids?.length === 1 ? 'analysis' : 'analyses'}
                </span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <Calendar size={14} />
                  {new Date(p.updated_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: '450px' }}>
            <div className="modal-header">
              <h3 className="modal-title">Confirm Deletion</h3>
            </div>
            <p style={{ color: 'var(--color-text-muted)', fontSize: '0.95rem' }}>
              Are you sure you want to delete this product? All historical analyses, uploaded specifications, 
              and saved artwork versions will be permanently removed.
            </p>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowConfirmModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--color-mismatch)', width: 'auto' }}
                onClick={confirmDelete}
              >
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
