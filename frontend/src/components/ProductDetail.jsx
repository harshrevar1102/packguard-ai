import React, { useState, useEffect } from 'react';
import { ArrowLeft, PlusCircle, Trash2, Calendar, FileText, ChevronRight, AlertCircle, ArrowUpRight } from 'lucide-react';

export default function ProductDetail({ productId, onNavigate, onSelectAnalysis, onStartNewAnalysisForProduct }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null); // { type: 'product' | 'analysis', id: str }

  useEffect(() => {
    fetchProductDetail();
  }, [productId]);

  const fetchProductDetail = async () => {
    try {
      setLoading(true);
      const res = await fetch(`/api/products/${productId}`);
      if (!res.ok) throw new Error('Product not found');
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteProduct = () => {
    setDeleteTarget({ type: 'product', id: productId });
  };

  const handleDeleteAnalysis = (e, analysisId) => {
    e.stopPropagation();
    setDeleteTarget({ type: 'analysis', id: analysisId });
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;

    try {
      if (deleteTarget.type === 'product') {
        const res = await fetch(`/api/products/${productId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete product');
        onNavigate('existing');
      } else {
        const res = await fetch(`/api/products/${productId}/analyses/${deleteTarget.id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete analysis');
        setDeleteTarget(null);
        fetchProductDetail();
      }
    } catch (err) {
      alert('Delete failed: ' + err.message);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--color-text-muted)' }}>
        Loading product details...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div>
        <div className="nav-breadcrumbs">
          <span className="back-link" onClick={() => onNavigate('existing')}>
            <ArrowLeft size={16} /> Back to Products
          </span>
        </div>
        <div className="conflict-alert">
          <h4><AlertCircle size={18} /> Error</h4>
          <p>{error || 'Product not found.'}</p>
        </div>
      </div>
    );
  }

  const { product, analyses } = data;

  return (
    <div>
      <div className="nav-breadcrumbs">
        <span className="back-link" onClick={() => onNavigate('existing')}>
          <ArrowLeft size={16} /> Back to Products
        </span>
      </div>

      <div className="page-header">
        <div>
          <h2 className="page-title">{product.name}</h2>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginTop: '0.25rem' }}>
            Created: {new Date(product.created_at).toLocaleDateString()} • {analyses.length} Total {analyses.length === 1 ? 'Analysis' : 'Analyses'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            className="btn-primary"
            style={{ width: 'auto' }}
            onClick={() => onStartNewAnalysisForProduct(product.name)}
          >
            <PlusCircle size={18} /> Start New Analysis
          </button>
          <button
            className="btn-secondary"
            style={{ color: 'var(--color-mismatch)' }}
            onClick={handleDeleteProduct}
          >
            <Trash2 size={16} /> Delete Product
          </button>
        </div>
      </div>

      <div style={{ marginTop: '2rem' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>
          Analysis History
        </h3>

        {analyses.length === 0 ? (
          <div className="empty-state">
            <FileText size={40} className="empty-state-icon" />
            <h4>No analyses available for this product</h4>
            <p>Start a new analysis to verify artwork against product specifications.</p>
            <button
              className="btn-primary"
              style={{ width: 'auto', marginTop: '1rem' }}
              onClick={() => onStartNewAnalysisForProduct(product.name)}
            >
              Start First Analysis
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {analyses.map((anl) => (
              <div
                key={anl.id}
                className="product-card"
                style={{ cursor: 'pointer', padding: '1.25rem' }}
                onClick={() => onSelectAnalysis(anl)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.35rem' }}>
                      <span style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--color-text-main)' }}>
                        Analysis: {anl.id}
                      </span>
                      <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                        {new Date(anl.timestamp).toLocaleString()}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                      Artwork: <strong style={{ color: 'var(--color-text-main)' }}>{anl.artwork_file}</strong> • Specifications: {anl.spec_files?.join(', ')}
                    </div>

                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                      <span className="status-badge Mismatch">
                        {anl.summary?.total_mismatches || 0} Mismatches
                      </span>
                      <span className="status-badge Needs-Review">
                        {anl.summary?.total_needs_review || 0} Needs Review
                      </span>
                      <span className="status-badge Match">
                        {anl.summary?.total_matches || 0} Matches
                      </span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '0.85rem', padding: '0.4rem 0.75rem' }}
                      onClick={() => onSelectAnalysis(anl)}
                    >
                      View Results <ArrowUpRight size={15} />
                    </button>
                    <button
                      className="delete-icon-btn"
                      title="Delete this analysis"
                      onClick={(e) => handleDeleteAnalysis(e, anl.id)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="modal-backdrop">
          <div className="modal-content" style={{ maxWidth: '450px' }}>
            <div className="modal-header">
              <h3 className="modal-title">
                {deleteTarget.type === 'product' ? 'Delete Product' : 'Delete Analysis'}
              </h3>
            </div>
            <p style={{ color: 'var(--color-text-muted)', fontSize: '0.95rem' }}>
              {deleteTarget.type === 'product'
                ? 'Are you sure you want to permanently delete this product, all its analyses, and saved artwork versions?'
                : 'Are you sure you want to delete this historical analysis record?'}
            </p>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                style={{ background: 'var(--color-mismatch)', width: 'auto' }}
                onClick={confirmDelete}
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
