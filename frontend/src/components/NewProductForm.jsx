import React, { useState } from 'react';
import { ArrowLeft, Upload, FileSpreadsheet, FileText, X, AlertTriangle, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function NewProductForm({ onNavigate, onAnalysisComplete, initialProductName = '' }) {
  const [productName, setProductName] = useState(initialProductName);
  const [specFiles, setSpecFiles] = useState([]);
  const [artworkFile, setArtworkFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const [conflictData, setConflictData] = useState(null);

  // Drag states for visual feedback
  const [isDraggingSpec, setIsDraggingSpec] = useState(false);
  const [isDraggingArtwork, setIsDraggingArtwork] = useState(false);

  const processSpecFiles = (files) => {
    setValidationError(null);
    setConflictData(null);
    const validFiles = [];

    for (const f of files) {
      const ext = f.name.toLowerCase();
      if (ext.endsWith('.xlsx') || ext.endsWith('.xls')) {
        // Prevent duplicate filenames in the same batch
        validFiles.push(f);
      } else {
        setValidationError(`Unsupported file format: "${f.name}". Only Excel files (.xlsx, .xls) are accepted.`);
        return;
      }
    }

    setSpecFiles((prev) => {
      // Avoid duplicates with same name
      const existingNames = new Set(prev.map((file) => file.name));
      const newUnique = validFiles.filter((file) => !existingNames.has(file.name));
      return [...prev, ...newUnique];
    });
  };

  const handleSpecFilesChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      processSpecFiles(Array.from(e.target.files));
      e.target.value = ''; // Reset input to allow re-selection
    }
  };

  const removeSpecFile = (index) => {
    setSpecFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const processArtworkFile = (file) => {
    setValidationError(null);
    setConflictData(null);
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setValidationError(`Unsupported artwork format: "${file.name}". Packaging artwork must be a PDF file (.pdf).`);
      return;
    }
    setArtworkFile(file);
  };

  const handleArtworkFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      processArtworkFile(e.target.files[0]);
      e.target.value = ''; // Reset input
    }
  };

  // Spec Drop Handlers
  const handleSpecDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingSpec(true);
  };

  const handleSpecDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingSpec(false);
  };

  const handleSpecDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingSpec(false);
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processSpecFiles(Array.from(e.dataTransfer.files));
    }
  };

  // Artwork Drop Handlers
  const handleArtworkDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingArtwork(true);
  };

  const handleArtworkDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingArtwork(false);
  };

  const handleArtworkDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingArtwork(false);
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processArtworkFile(e.dataTransfer.files[0]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setValidationError(null);
    setConflictData(null);

    const cleanName = productName.trim();
    if (!cleanName) {
      setValidationError('Please enter a product name.');
      return;
    }

    if (specFiles.length === 0) {
      setValidationError('Please upload at least one Excel specification document (.xlsx or .xls).');
      return;
    }

    if (!artworkFile) {
      setValidationError('Please upload one packaging artwork PDF (.pdf).');
      return;
    }

    const formData = new FormData();
    formData.append('product_name', cleanName);
    specFiles.forEach((file) => {
      formData.append('spec_files', file);
    });
    formData.append('artwork_file', artworkFile);

    try {
      setLoading(true);
      const res = await fetch('/api/analyze', {
        method: 'POST',
        body: formData,
      });

      if (res.status === 409) {
        // Contradiction detected across specification files!
        const conflict = await res.json();
        setConflictData(conflict);
        return;
      }

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Failed to complete analysis' }));
        throw new Error(errorData.detail || 'Analysis request failed.');
      }

      const analysis = await res.json();
      onAnalysisComplete(analysis);
    } catch (err) {
      setValidationError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="nav-breadcrumbs">
        <span className="back-link" onClick={() => onNavigate('home')}>
          <ArrowLeft size={16} /> Back to Options
        </span>
      </div>

      <div className="form-card">
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          {initialProductName ? `Analyse: ${initialProductName}` : 'Analyse New Product'}
        </h2>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', marginBottom: '2rem' }}>
          Upload product specification files and one artwork PDF. The engine will check for specification
          contradictions and verify all artwork declarations.
        </p>

        {validationError && (
          <div className="conflict-alert" style={{ background: '#fef2f2', borderColor: '#fecaca', color: '#b91c1c' }}>
            <h4><AlertCircle size={18} /> Validation Error</h4>
            <p>{validationError}</p>
          </div>
        )}

        {/* Contradiction Alert Section as required by Section 2 */}
        {conflictData && (
          <div className="conflict-alert">
            <h4><AlertTriangle size={20} /> Specification Contradiction Detected</h4>
            <p>
              Analysis was stopped because the uploaded specification documents contain contradictory or incompatible
              product information. Please review the conflicting values below and upload the correct, consistent documents.
            </p>
            <p style={{ fontWeight: 600, color: '#7f1d1d' }}>
              {conflictData.conflict_summary}
            </p>

            {conflictData.conflicting_entries && conflictData.conflicting_entries.length > 0 && (
              <table className="conflict-entries-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Sheet & Cell</th>
                    <th>Declared Value</th>
                  </tr>
                </thead>
                <tbody>
                  {conflictData.conflicting_entries.map((entry, idx) => (
                    <tr key={idx}>
                      <td>{entry.filename}</td>
                      <td>{entry.sheet}!{entry.cell}</td>
                      <td style={{ fontWeight: 600 }}>{entry.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Product Name</label>
            <input
              type="text"
              className="form-input"
              placeholder="e.g. Organic Almond Butter 500g"
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">
              Specification Documents (Excel .xlsx / .xls)
              <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.5rem' }}>
                (Multiple files allowed)
              </span>
            </label>
            <label
              className={`file-upload-zone ${isDraggingSpec ? 'dragging' : ''}`}
              style={{ display: 'block' }}
              onDragEnter={handleSpecDragOver}
              onDragOver={handleSpecDragOver}
              onDragLeave={handleSpecDragLeave}
              onDrop={handleSpecDrop}
            >
              <input
                type="file"
                multiple
                accept=".xlsx,.xls"
                onChange={handleSpecFilesChange}
                style={{ display: 'none' }}
                disabled={loading}
              />
              <FileSpreadsheet
                size={34}
                color={isDraggingSpec ? '#0369a1' : '#0284c7'}
                style={{ margin: '0 auto', transition: 'transform 0.15s', transform: isDraggingSpec ? 'scale(1.15)' : 'none' }}
              />
              <p style={{ fontWeight: 600, color: isDraggingSpec ? '#0284c7' : 'var(--color-text-main)' }}>
                {isDraggingSpec
                  ? 'Drop Excel specification files here...'
                  : 'Drag & drop Excel files here, or click to browse'}
              </p>
              <p>Supports .xlsx and .xls formats (multiple files accepted)</p>
            </label>

            {specFiles.length > 0 && (
              <div className="file-tags-list">
                {specFiles.map((f, i) => (
                  <span key={i} className="file-tag">
                    <FileSpreadsheet size={14} color="#0284c7" />
                    {f.name}
                    <X
                      size={14}
                      className="file-tag-remove"
                      onClick={() => removeSpecFile(i)}
                    />
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">
              Packaging Artwork PDF
              <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '0.5rem' }}>
                (Exactly 1 file)
              </span>
            </label>
            <label
              className={`file-upload-zone ${isDraggingArtwork ? 'dragging' : ''}`}
              style={{ display: 'block' }}
              onDragEnter={handleArtworkDragOver}
              onDragOver={handleArtworkDragOver}
              onDragLeave={handleArtworkDragLeave}
              onDrop={handleArtworkDrop}
            >
              <input
                type="file"
                accept=".pdf"
                onChange={handleArtworkFileChange}
                style={{ display: 'none' }}
                disabled={loading}
              />
              <FileText
                size={34}
                color={isDraggingArtwork ? '#c2410c' : '#ea580c'}
                style={{ margin: '0 auto', transition: 'transform 0.15s', transform: isDraggingArtwork ? 'scale(1.15)' : 'none' }}
              />
              <p style={{ fontWeight: 600, color: isDraggingArtwork ? '#ea580c' : 'var(--color-text-main)' }}>
                {isDraggingArtwork
                  ? 'Drop packaging artwork PDF here...'
                  : artworkFile
                  ? `Selected: ${artworkFile.name}`
                  : 'Drag & drop artwork PDF here, or click to browse'}
              </p>
              <p>Supports 1 native PDF artwork document</p>
            </label>
          </div>

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Validating and Analysing Documents...' : 'Analyse Documents'}
          </button>
        </form>
      </div>
    </div>
  );
}
