import React from 'react';
import { X, FileText, CheckCircle2, AlertTriangle, AlertCircle, HelpCircle } from 'lucide-react';

export default function DetailsModal({ finding, onClose }) {
  if (!finding) return null;

  const getStatusIcon = (status) => {
    switch (status) {
      case 'Match':
        return <CheckCircle2 size={18} color="var(--color-match)" />;
      case 'Needs Review':
        return <AlertTriangle size={18} color="var(--color-review)" />;
      case 'Mismatch':
        return <AlertCircle size={18} color="var(--color-mismatch)" />;
      default:
        return <HelpCircle size={18} color="var(--color-notchecked)" />;
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-content" style={{ maxWidth: '650px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {getStatusIcon(finding.status)}
            <h3 className="modal-title">{finding.field_name}</h3>
          </div>
          <X className="modal-close-btn" size={20} onClick={onClose} />
        </div>

        <div>
          <div className="evidence-field-row">
            <div className="evidence-field-label">Finding Status</div>
            <span className={`status-badge ${finding.status.replace(/\s+/g, '-')}`}>
              {finding.status}
            </span>
          </div>

          <div className="evidence-field-row">
            <div className="evidence-field-label">Explanation & Analysis</div>
            <div className="evidence-field-val">
              {finding.explanation}
            </div>
          </div>

          {finding.ai_analysis && (
            <div className="evidence-field-row" style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '0.65rem 0.85rem', borderRadius: '6px', marginBottom: '0.75rem' }}>
              <div className="evidence-field-label" style={{ color: '#166534', fontWeight: 600 }}>AI Semantic Verification</div>
              <div className="evidence-field-val" style={{ color: '#14532d', fontSize: '0.875rem', lineHeight: 1.4 }}>
                {finding.ai_analysis}
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div className="evidence-field-row">
              <div className="evidence-field-label">Specification Value</div>
              <div className="evidence-field-val" style={{ fontWeight: 600 }}>
                {finding.spec_value || 'None'}
              </div>
            </div>

            <div className="evidence-field-row">
              <div className="evidence-field-label">Artwork Declared Value</div>
              <div className="evidence-field-val" style={{ fontWeight: 600 }}>
                {finding.artwork_value || 'Not found'}
              </div>
            </div>
          </div>

          {finding.expected_value && (
            <div className="evidence-field-row">
              <div className="evidence-field-label">Expected Value (Authoritative)</div>
              <div className="evidence-field-val" style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
                {finding.expected_value}
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '0.5rem' }}>
            <div className="evidence-field-row">
              <div className="evidence-field-label">Source Evidence (Excel)</div>
              <div className="evidence-field-val">
                {finding.spec_source ? (
                  <div>
                    <div><strong>File:</strong> {finding.spec_source.filename}</div>
                    <div><strong>Sheet:</strong> {finding.spec_source.sheet}</div>
                    <div><strong>Cell:</strong> {finding.spec_source.cell}</div>
                    {finding.spec_source.label && (
                      <div><strong>Label:</strong> {finding.spec_source.label}</div>
                    )}
                  </div>
                ) : (
                  <span style={{ color: 'var(--color-text-dim)' }}>No specification cell recorded</span>
                )}
              </div>
            </div>

            <div className="evidence-field-row">
              <div className="evidence-field-label">Artwork Evidence (PDF)</div>
              <div className="evidence-field-val">
                {finding.artwork_source ? (
                  <div>
                    <div><strong>File:</strong> {finding.artwork_source.filename}</div>
                    <div><strong>Page:</strong> Page {finding.artwork_source.page}</div>
                    {finding.artwork_source.bbox && (
                      <div><strong>BBox:</strong> [{finding.artwork_source.bbox.join(', ')}]</div>
                    )}
                    {finding.artwork_source.font_name && (
                      <div><strong>Font:</strong> {finding.artwork_source.font_name} ({finding.artwork_source.font_size}pt)</div>
                    )}
                  </div>
                ) : (
                  <span style={{ color: 'var(--color-text-dim)' }}>Not located on artwork</span>
                )}
              </div>
            </div>
          </div>

          <div className="evidence-field-row" style={{ marginTop: '0.5rem' }}>
            <div className="evidence-field-label">Automatic Fix Status</div>
            <div className="evidence-field-val">
              {finding.status === 'Mismatch' || finding.safe_fix_available ? (
                <span style={{ color: 'var(--color-match)', fontWeight: 600 }}>
                  Correction candidate available with visual layout preview and versioning.
                </span>
              ) : (
                <span style={{ color: 'var(--color-review)', fontWeight: 500 }}>
                  {finding.fix_explanation || 'No correction needed for matched items.'}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
