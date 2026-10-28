import React, { useState } from 'react';
import { X, Mail, Send, AlertCircle, Copy, Check } from 'lucide-react';

export default function EmailModal({ productId, analysisId, analysis, onClose }) {
  const [recipient, setRecipient] = useState('');
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleOpenGmail = async (e) => {
    if (e) e.preventDefault();
    const newTab = window.open('about:blank', '_blank');
    try {
      setLoading(true);
      const res = await fetch(`/api/products/${productId}/analyses/${analysisId}/email-report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipient: recipient.trim() })
      });

      if (!res.ok) throw new Error('Failed to generate email report');
      const data = await res.json();
      setReportData(data);

      try {
        if (navigator.clipboard) {
          await navigator.clipboard.writeText(`Subject: ${data.subject}\n\n${data.body}`);
        }
      } catch (_) {}

      if (newTab) {
        newTab.location.href = data.gmail_url;
      } else {
        window.location.href = data.gmail_url;
      }
    } catch (err) {
      if (newTab) newTab.close();
      alert('Email report error: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = () => {
    if (!reportData) return;
    navigator.clipboard.writeText(`Subject: ${reportData.subject}\n\n${reportData.body}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-content" style={{ maxWidth: '680px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Mail size={22} color="var(--color-primary)" />
            <h3 className="modal-title">Email Artwork Issue Report</h3>
          </div>
          <X className="modal-close-btn" size={20} onClick={onClose} />
        </div>

        <form onSubmit={handleOpenGmail}>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label className="form-label">Recipient Email Address (Optional)</label>
            <input
              type="email"
              className="form-input"
              placeholder="e.g. packaging.designer@company.com (or enter directly in Gmail)"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
            />
          </div>

          <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', color: '#166534', padding: '0.75rem 1rem', borderRadius: '6px', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
            <strong>Ready to Send:</strong> All verification details, cell references, and discrepancies are formatted directly inside the email body. No file attachments are needed.
          </div>

          <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" style={{ width: 'auto' }} disabled={loading}>
              <Send size={16} /> {loading ? 'Opening Gmail...' : 'Open in Gmail (Active Account)'}
            </button>
          </div>
        </form>

        {reportData && (
          <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Draft Preview:</span>
              <button className="btn-secondary" style={{ padding: '0.2rem 0.6rem', fontSize: '0.8rem' }} onClick={copyToClipboard}>
                {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy Text</>}
              </button>
            </div>
            <textarea
              readOnly
              rows={8}
              value={`Subject: ${reportData.subject}\n\n${reportData.body}`}
              style={{ width: '100%', fontSize: '0.8rem', padding: '0.5rem', border: '1px solid var(--color-border)', borderRadius: '4px', fontFamily: 'monospace' }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
