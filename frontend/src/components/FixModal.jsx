import React, { useState } from 'react';
import { X, Check, RotateCcw, AlertTriangle, ShieldCheck } from 'lucide-react';

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

          <div style={{ textAlign: 'center', background: '#1e293b', padding: '1rem', borderRadius: '8px', overflow: 'hidden' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.5rem', textAlign: 'left' }}>
              Candidate Page Rendering Preview:
            </div>
            <img
              src={`${previewData.candidate_image_url}&t=${Date.now()}`}
              alt="Candidate Preview"
              style={{ maxWidth: '100%', maxHeight: '420px', display: 'inline-block', boxShadow: '0 4px 10px rgba(0,0,0,0.5)', background: 'white' }}
            />
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
