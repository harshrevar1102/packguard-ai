import React, { useState } from 'react';
import { X, Check, RotateCcw, AlertTriangle, ShieldCheck, ZoomIn, ZoomOut } from 'lucide-react';

export default function FixModal({
  productId,
  analysisId,
  finding,
  previewData,
  onClose,
  onSaveSuccess
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [previewZoom, setPreviewZoom] = useState(1);
  const [candidateImageUrl] = useState(
    () => `${previewData.candidate_image_url}&t=${Date.now()}`
  );

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      const res = await fetch(`/api/products/${productId}/analyses/${analysisId}/fix/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ finding_id: finding.id })
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({ detail: 'Failed to save correction' }));
        throw new Error(data.detail || 'Save failed');
      }

      const result = await res.json();
      onSaveSuccess(result.analysis);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-content" style={{ maxWidth: '750px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldCheck size={22} color="var(--color-primary)" />
            <h3 className="modal-title">Review Proposed Safe Fix</h3>
          </div>
          <X className="modal-close-btn" size={20} onClick={onClose} />
        </div>

        {error && (
          <div className="conflict-alert">
            <h4><AlertTriangle size={18} /> Error Saving Fix</h4>
            <p>{error}</p>
          </div>
        )}

        <div style={{ marginBottom: '1.25rem' }}>
          <p style={{ fontSize: '0.9rem', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
            A temporary working copy has been prepared. Review the candidate rendering below before accepting.
            Accepting will create an immutable, numbered version without modifying the original artwork PDF.
          </p>

          <div className="finding-values-grid" style={{ marginBottom: '1rem' }}>
            <div>
              <div className="finding-val-label">Current Artwork Text</div>
              <div
                className="finding-val-content"
                style={{
                  color: 'var(--color-mismatch)',
                  maxHeight: '110px',
                  overflowY: 'auto',
                  wordBreak: 'break-word',
                  whiteSpace: 'pre-wrap'
                }}
              >
                {finding.artwork_value}
              </div>
            </div>
            <div>
              <div className="finding-val-label">Proposed Replacement (Specification)</div>
              <div
                className="finding-val-content"
                style={{
                  color: 'var(--color-match)',
                  maxHeight: '110px',
                  overflowY: 'auto',
                  wordBreak: 'break-word',
                  whiteSpace: 'pre-wrap'
                }}
              >
                {previewData.replacement}
              </div>
            </div>
          </div>

          <div style={{ fontSize: '0.85rem', color: '#0369a1', background: '#e0f2fe', padding: '0.65rem 0.85rem', borderRadius: '6px', marginBottom: '1rem' }}>
            <strong>Visual Candidate Ready:</strong> Review candidate typography and positioning below before committing.
          </div>

          <div style={{ background: '#1e293b', padding: '1rem', borderRadius: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                Candidate Page Rendering Preview:
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ padding: '0.25rem 0.4rem' }}
                  title="Zoom out"
                  aria-label="Zoom out candidate preview"
                  onClick={() => setPreviewZoom((zoom) => Math.max(0.75, zoom - 0.25))}
                  disabled={previewZoom <= 0.75}
                >
                  <ZoomOut size={14} />
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ padding: '0.25rem 0.45rem', minWidth: '46px', fontSize: '0.75rem', fontWeight: 600 }}
                  title="Reset zoom to 100%"
                  onClick={() => setPreviewZoom(1)}
                >
                  {Math.round(previewZoom * 100)}%
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ padding: '0.25rem 0.4rem' }}
                  title="Zoom in"
                  aria-label="Zoom in candidate preview"
                  onClick={() => setPreviewZoom((zoom) => Math.min(3, zoom + 0.25))}
                  disabled={previewZoom >= 3}
                >
                  <ZoomIn size={14} />
                </button>
              </div>
            </div>
            <div style={{ maxHeight: '420px', overflow: 'auto', textAlign: 'center', borderRadius: '4px' }}>
              <img
                src={candidateImageUrl}
                alt="Candidate Preview"
                style={{
                  width: `${previewZoom * 100}%`,
                  maxWidth: 'none',
                  display: 'block',
                  margin: '0 auto',
                  boxShadow: '0 4px 10px rgba(0,0,0,0.5)',
                  background: 'white'
                }}
              />
            </div>
          </div>
        </div>

        <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>
            <RotateCcw size={16} /> Undo Candidate (Discard)
          </button>

          <button className="btn-primary" style={{ width: 'auto' }} onClick={handleSave} disabled={saving}>
            <Check size={16} /> {saving ? 'Saving New Version...' : 'Save & Commit Version'}
          </button>
        </div>
      </div>
    </div>
  );
}
