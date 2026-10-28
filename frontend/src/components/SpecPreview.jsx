import React, { useState, useEffect } from 'react';
import { FileSpreadsheet, AlertCircle } from 'lucide-react';

export default function SpecPreview({ productId, analysisId, selectedFinding }) {
  const [matrixData, setMatrixData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const specSource = selectedFinding?.spec_source;
  const specKey = specSource ? `${specSource.filename}_${specSource.sheet}_${specSource.cell}` : '';
  const [cache, setCache] = useState({});

  useEffect(() => {
    if (!specSource || !specSource.filename || !specSource.sheet || !specSource.cell) {
      setMatrixData(null);
      return;
    }

    if (cache[specKey]) {
      setMatrixData(cache[specKey]);
      return;
    }

    const fetchPreview = async () => {
      try {
        setLoading(true);
        setError(null);
        const url = `/api/products/${productId}/analyses/${analysisId}/spec/preview?filename=${encodeURIComponent(
          specSource.filename
        )}&sheet=${encodeURIComponent(specSource.sheet)}&cell=${encodeURIComponent(specSource.cell)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Could not load cell context');
        const data = await res.json();
        setMatrixData(data);
        setCache((prev) => ({ ...prev, [specKey]: data }));
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchPreview();
  }, [productId, analysisId, specKey]);

  return (
    <div className="preview-box">
      <div className="preview-box-header">
        <h4 className="preview-box-title">
          <FileSpreadsheet size={18} color="#0284c7" /> Specification Document Preview
        </h4>
        {specSource && (
          <span style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)', fontWeight: 500 }}>
            {specSource.filename} • {specSource.sheet}!{specSource.cell}
          </span>
        )}
      </div>

      {!selectedFinding ? (
        <p style={{ color: 'var(--color-text-muted)', fontSize: '0.9rem', fontStyle: 'italic', padding: '1rem 0' }}>
          Select a finding on the left to inspect its supporting specification sheet and cell context.
        </p>
      ) : !specSource ? (
        <div className="preview-limitation-banner">
          <AlertCircle size={15} style={{ verticalAlign: 'middle', marginRight: '0.35rem' }} />
          <strong>No specification cell reference:</strong> This item originated as an unverified declaration
          found on the packaging artwork, or lacks a direct spreadsheet cell.
        </div>
      ) : loading ? (
        <div style={{ padding: '1.5rem', textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '0.85rem' }}>
          Loading sheet context...
        </div>
      ) : error ? (
        <div className="preview-limitation-banner">
          <AlertCircle size={15} style={{ verticalAlign: 'middle', marginRight: '0.35rem' }} />
          {error}
        </div>
      ) : matrixData ? (
        <div>
          <div style={{ fontSize: '0.85rem', marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between' }}>
            <span>Target Cell: <strong>{matrixData.target_cell}</strong></span>
            <span>Target Value: <strong>"{matrixData.target_value}"</strong></span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="spec-matrix-table">
              <tbody>
                {matrixData.matrix.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {row.map((cell) => (
                      <td
                        key={cell.coordinate}
                        className={cell.is_target ? 'target-cell' : ''}
                        title={cell.coordinate}
                      >
                        <div style={{ fontSize: '0.7rem', color: 'var(--color-text-dim)', marginBottom: '0.15rem' }}>
                          {cell.coordinate}
                        </div>
                        <div style={{ wordBreak: 'break-word', minWidth: '80px' }}>
                          {cell.value || <span style={{ color: '#cbd5e1' }}>—</span>}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
