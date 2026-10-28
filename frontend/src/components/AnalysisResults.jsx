import React, { useState } from 'react';
import {
  ArrowLeft,
  Download,
  Mail,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Wrench,
  Info,
  ChevronDown,
  ChevronUp,
  History,
  CheckSquare,
  Square
} from 'lucide-react';
import ArtworkPreview from './ArtworkPreview';
import SpecPreview from './SpecPreview';
import DetailsModal from './DetailsModal';
import FixModal from './FixModal';
import EmailModal from './EmailModal';

export default function AnalysisResults({ analysis: initialAnalysis, onNavigate, onBackToProduct }) {
  const [analysis, setAnalysis] = useState(initialAnalysis);
  const [selectedFindingId, setSelectedFindingId] = useState(
    initialAnalysis.findings?.[0]?.id || null
  );
  const [checkedFindingIds, setCheckedFindingIds] = useState(new Set());
  const [activeFilter, setActiveFilter] = useState('All');
  const [showHistoryDetails, setShowHistoryDetails] = useState(false);

  // Modals state
  const [detailsFinding, setDetailsFinding] = useState(null);
  const [fixModalData, setFixModalData] = useState(null); // { finding, previewData }
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [fixLoadingId, setFixLoadingId] = useState(null);

  const selectedFinding = analysis.findings?.find((f) => f.id === selectedFindingId) || null;

  // Toggle checkbox for a finding
  const toggleCheckbox = (e, id) => {
    e.stopPropagation();
    setCheckedFindingIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Toggle select all
  const toggleSelectAll = () => {
    if (checkedFindingIds.size === filteredFindings.length) {
      setCheckedFindingIds(new Set());
    } else {
      setCheckedFindingIds(new Set(filteredFindings.map((f) => f.id)));
    }
  };

  // Safe Fix preview trigger
  const handleTriggerFix = async (e, finding) => {
    e.stopPropagation();
    try {
      setFixLoadingId(finding.id);
      const res = await fetch(
        `/api/products/${analysis.product_id}/analyses/${analysis.id}/fix/preview`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ finding_id: finding.id })
        }
      );
      const data = await res.json();
      if (!data.success) {
        alert(data.message || 'Cannot apply safe fix.');
        return;
      }
      setFixModalData({ finding, previewData: data });
    } catch (err) {
      alert('Error initiating fix preview: ' + err.message);
    } finally {
      setFixLoadingId(null);
    }
  };

  const handleFixSaved = (updatedAnalysis) => {
    setAnalysis(updatedAnalysis);
  };

  const [emailLoading, setEmailLoading] = useState(false);

  // Directly redirect user to Gmail compose interface with full report in text format
  const handleEmailReportClick = async () => {
    // Open new tab immediately on user click to prevent popup blockers
    const newTab = window.open('about:blank', '_blank');
    try {
      setEmailLoading(true);
      const res = await fetch(`/api/products/${analysis.product_id}/analyses/${analysis.id}/email-report`);
      if (!res.ok) throw new Error('Failed to generate email report');
      const data = await res.json();

      // Copy text to clipboard as convenience backup
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
      alert('Error opening Gmail compose: ' + err.message);
    } finally {
      setEmailLoading(false);
    }
  };

  // Filter findings
  const filteredFindings = (analysis.findings || []).filter((f) => {
    if (activeFilter === 'All') return true;
    return f.status === activeFilter;
  });

  const comparison = analysis.comparison_with_previous;

  return (
    <div>
      <div className="nav-breadcrumbs">
        <span className="back-link" onClick={() => onBackToProduct(analysis.product_id)}>
          <ArrowLeft size={16} /> Back to Product ({analysis.product_name})
        </span>
      </div>

      {/* Page Title & Product Header */}
      <div className="page-header" style={{ marginBottom: '1.25rem' }}>
        <div>
          <h2 className="page-title">{analysis.product_name} — Verification Results</h2>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '0.875rem', marginTop: '0.2rem' }}>
            Analysis ID: {analysis.id} • {new Date(analysis.timestamp).toLocaleString()} • Artwork: {analysis.artwork_file}
          </p>
        </div>

        <div className="action-buttons-group">
          {/* Version badge */}
          {analysis.active_version_id && analysis.active_version_id !== 'v0_original' && (
            <span style={{ fontSize: '0.85rem', fontWeight: 600, background: '#e0f2fe', color: '#0369a1', padding: '0.35rem 0.75rem', borderRadius: '6px' }}>
              Version: {analysis.active_version_id}
            </span>
          )}

          {/* CSV Export Button */}
          <a
            href={`/api/products/${analysis.product_id}/analyses/${analysis.id}/export/csv`}
            download
            className="btn-secondary"
            title="Export all analysis findings and evidence to CSV"
          >
            <Download size={16} /> CSV Export
          </a>

          {/* Email Report Button (Direct Gmail Redirection) */}
          <button
            className="btn-secondary"
            onClick={handleEmailReportClick}
            disabled={emailLoading}
            title="Open Gmail compose with full discrepancy report in body (using your logged-in Google account)"
          >
            <Mail size={16} /> {emailLoading ? 'Opening Gmail...' : 'Email Report'}
          </button>
        </div>
      </div>

      {/* 1. Results Summary Metrics */}
      <div className="results-summary-bar">
        <div className="summary-metric-card">
          <div className="metric-badge mismatch">
            <AlertCircle size={22} />
          </div>
          <div className="metric-info">
            <h5>Mismatches</h5>
            <span>{analysis.summary?.total_mismatches ?? 0}</span>
          </div>
        </div>

        <div className="summary-metric-card">
          <div className="metric-badge review">
            <AlertTriangle size={22} />
          </div>
          <div className="metric-info">
            <h5>Needs Review</h5>
            <span>{analysis.summary?.total_needs_review ?? 0}</span>
          </div>
        </div>

        <div className="summary-metric-card">
          <div className="metric-badge match">
            <CheckCircle2 size={22} />
          </div>
          <div className="metric-info">
            <h5>Matches</h5>
            <span>{analysis.summary?.total_matches ?? 0}</span>
          </div>
        </div>

        <div className="summary-metric-card">
          <div className="metric-badge notchecked">
            <HelpCircle size={22} />
          </div>
          <div className="metric-info">
            <h5>Not Checked</h5>
            <span>{analysis.summary?.total_not_checked ?? 0}</span>
          </div>
        </div>
      </div>

      {/* 2. Historical Comparison Section (Section 7) */}
      {comparison && (
        <div className="history-comparison-card">
          <div
            className="history-comparison-header"
            onClick={() => setShowHistoryDetails(!showHistoryDetails)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <History size={18} color="var(--color-primary)" />
              <strong style={{ fontSize: '0.95rem' }}>
                Comparison with Previous Analysis ({comparison.previous_analysis_id})
              </strong>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}>
              <span className="comparison-pill resolved">{comparison.resolved_count} Resolved</span>
              <span className="comparison-pill persistent">{comparison.persistent_count} Persistent</span>
              <span className="comparison-pill new">{comparison.new_count} New</span>
              {showHistoryDetails ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
          </div>

          {showHistoryDetails && (
            <div className="change-descriptions-list">
              <div style={{ marginBottom: '0.5rem', fontWeight: 600 }}>
                Historical Audit Delta:
              </div>
              {comparison.change_descriptions.length === 0 ? (
                <p>No changes detected between consecutive analyses.</p>
              ) : (
                <ul>
                  {comparison.change_descriptions.map((desc, idx) => (
                    <li key={idx}>{desc}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* 3. Main Split Layout */}
      <div className="results-split-layout">
        {/* Left Column: Findings List with Checkboxes and Controls */}
        <div className="findings-panel">
          <div className="findings-panel-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                className="btn-secondary"
                style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
                onClick={toggleSelectAll}
              >
                {checkedFindingIds.size > 0 && checkedFindingIds.size === filteredFindings.length ? (
                  <CheckSquare size={14} color="var(--color-primary)" />
                ) : (
                  <Square size={14} />
                )}
                <span style={{ marginLeft: '0.35rem' }}>Select All</span>
              </button>
              <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>
                ({filteredFindings.length} findings)
              </span>
            </div>

            <div className="filter-pills">
              {['All', 'Mismatch', 'Needs Review', 'Match', 'Not Checked'].map((filter) => (
                <button
                  key={filter}
                  className={`filter-pill ${activeFilter === filter ? 'active' : ''}`}
                  onClick={() => setActiveFilter(filter)}
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>

          <div className="findings-list">
            {filteredFindings.map((f) => {
              const isSelected = f.id === selectedFindingId;
              const isChecked = checkedFindingIds.has(f.id);

              return (
                <div
                  key={f.id}
                  className={`finding-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedFindingId(f.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="finding-card-header">
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={(e) => toggleCheckbox(e, f.id)}
                      onClick={(e) => e.stopPropagation()}
                      style={{ cursor: 'pointer', width: '16px', height: '16px' }}
                    />
                    <span className={`status-badge ${f.status.replace(/\s+/g, '-')}`}>
                      {f.status}
                    </span>
                    {f.ai_analysis && f.status === 'Match' && (
                      <span style={{ fontSize: '0.72rem', background: '#ecfdf5', color: '#047857', border: '1px solid #a7f3d0', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 600 }}>
                        AI Semantic Match
                      </span>
                    )}
                    <span className="finding-title">{f.field_name}</span>
                  </div>

                  <div className="finding-values-grid">
                    <div>
                      <div className="finding-val-label">Specification:</div>
                      <div className="finding-val-content">{f.spec_value}</div>
                    </div>
                    <div>
                      <div className="finding-val-label">Artwork:</div>
                      <div className="finding-val-content">{f.artwork_value}</div>
                    </div>
                  </div>

                  <p style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)', lineHeight: '1.4', marginBottom: '0.5rem' }}>
                    {f.explanation}
                  </p>

                  <div className="finding-actions">
                    <button
                      className="btn-small btn-details"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDetailsFinding(f);
                      }}
                      title="Inspect full source evidence and coordinates"
                    >
                      <Info size={14} /> Details
                    </button>

                    {f.status === 'Mismatch' && (
                      <button
                        className="btn-small btn-fix"
                        disabled={fixLoadingId === f.id}
                        onClick={(e) => handleTriggerFix(e, f)}
                        title="Preview and apply correction to PDF artwork"
                        style={{
                          opacity: 1,
                          cursor: fixLoadingId === f.id ? 'wait' : 'pointer'
                        }}
                      >
                        <Wrench size={14} />
                        {fixLoadingId === f.id ? 'Evaluating...' : 'Fix'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Previews */}
        <div className="previews-column">
          <ArtworkPreview
            productId={analysis.product_id}
            analysisId={analysis.id}
            selectedFinding={selectedFinding}
            activeVersionId={analysis.active_version_id}
            totalPages={analysis.total_pages || 1}
          />

          <SpecPreview
            productId={analysis.product_id}
            analysisId={analysis.id}
            selectedFinding={selectedFinding}
          />
        </div>
      </div>

      {/* Details Modal */}
      {detailsFinding && (
        <DetailsModal finding={detailsFinding} onClose={() => setDetailsFinding(null)} />
      )}

      {/* Safe Fix Candidate Modal */}
      {fixModalData && (
        <FixModal
          productId={analysis.product_id}
          analysisId={analysis.id}
          finding={fixModalData.finding}
          previewData={fixModalData.previewData}
          onClose={() => setFixModalData(null)}
          onSaveSuccess={handleFixSaved}
        />
      )}

      {/* Email Report Modal */}
      {showEmailModal && (
        <EmailModal
          productId={analysis.product_id}
          analysisId={analysis.id}
          analysis={analysis}
          onClose={() => setShowEmailModal(false)}
        />
      )}
    </div>
  );
}
