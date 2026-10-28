import React, { useState, useRef, useEffect } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Eye,
  AlertCircle,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Maximize2,
  X
} from 'lucide-react';

export default function ArtworkPreview({
  productId,
  analysisId,
  selectedFinding,
  activeVersionId,
  totalPages = 1
}) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);
  const [lightboxZoom, setLightboxZoom] = useState(1.5);

  const [imgNaturalSize, setImgNaturalSize] = useState({ width: 0, height: 0 });
  const [imgDisplaySize, setImgDisplaySize] = useState({ width: 0, height: 0 });
  const imgRef = useRef(null);
  const previewContainerRef = useRef(null);
  const lightboxContainerRef = useRef(null);

  const maxPages = Math.max(1, totalPages);

  // If a finding is selected and has a specific page, automatically navigate to that page
  useEffect(() => {
    if (selectedFinding?.artwork_source?.page) {
      const targetPage = Math.min(Math.max(1, selectedFinding.artwork_source.page), maxPages);
      setCurrentPage(targetPage);
    }
  }, [selectedFinding, maxPages]);

  useEffect(() => {
    if (previewContainerRef.current) {
      previewContainerRef.current.scrollTo({ left: 0, top: 0 });
    }
    if (lightboxContainerRef.current) {
      lightboxContainerRef.current.scrollTo({ left: 0, top: 0 });
    }
  }, [currentPage, isLightboxOpen]);

  const handleImageLoad = (e) => {
    setImgNaturalSize({
      width: e.target.naturalWidth,
      height: e.target.naturalHeight
    });
    updateDisplaySize();
  };

  const updateDisplaySize = () => {
    if (imgRef.current) {
      setImgDisplaySize({
        width: imgRef.current.clientWidth,
        height: imgRef.current.clientHeight
      });
    }
  };

  useEffect(() => {
    window.addEventListener('resize', updateDisplaySize);
    return () => window.removeEventListener('resize', updateDisplaySize);
  }, []);

  const handleZoomIn = () => {
    setZoom((prev) => Math.min(prev + 0.25, 2.5));
  };

  const handleZoomOut = () => {
    setZoom((prev) => Math.max(prev - 0.25, 0.75));
  };

  const handleResetZoom = () => {
    setZoom(1);
  };

  const handleImageClick = () => {
    // Toggle zoom on click (100% <-> 150%)
    setZoom((prev) => (prev === 1 ? 1.5 : 1));
  };

  // Compute highlight overlay styles
  const getHighlightStyle = (isModal = false) => {
    if (
      !selectedFinding ||
      !selectedFinding.artwork_source ||
      !selectedFinding.artwork_source.bbox ||
      selectedFinding.artwork_source.page !== currentPage ||
      imgNaturalSize.width === 0
    ) {
      return null;
    }

    const bbox = selectedFinding.artwork_source.bbox; // [x0, y0, x1, y1] in PDF points (72 DPI)
    const pdfWidthPoints = imgNaturalSize.width / (150 / 72);
    const pdfHeightPoints = imgNaturalSize.height / (150 / 72);

    const leftPercent = (bbox[0] / pdfWidthPoints) * 100;
    const topPercent = (bbox[1] / pdfHeightPoints) * 100;
    const widthPercent = ((bbox[2] - bbox[0]) / pdfWidthPoints) * 100;
    const heightPercent = ((bbox[3] - bbox[1]) / pdfHeightPoints) * 100;

    return {
      left: `${Math.max(0, leftPercent - 0.4)}%`,
      top: `${Math.max(0, topPercent - 0.4)}%`,
      width: `${Math.max(1, widthPercent + 0.8)}%`,
      height: `${Math.max(1.5, heightPercent + 0.8)}%`
    };
  };

  const highlightStyle = getHighlightStyle(false);
  const hasReliableLocation =
    selectedFinding?.artwork_source?.bbox && selectedFinding?.artwork_source?.page === currentPage;

  const imageUrl = `/api/products/${productId}/analyses/${analysisId}/artwork/image?page=${currentPage}${
    activeVersionId ? `&version_id=${activeVersionId}` : ''
  }&t=${activeVersionId || 'current'}`;

  return (
    <div className="preview-box">
      <div className="preview-box-header" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
        <h4 className="preview-box-title">
          <Eye size={18} color="var(--color-primary)" /> Packaging Artwork Preview
        </h4>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem' }}>
          {/* Zoom controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', marginRight: '0.5rem' }}>
            <button
              className="btn-secondary"
              style={{ padding: '0.25rem 0.45rem' }}
              title="Zoom out"
              onClick={handleZoomOut}
              disabled={zoom <= 0.75}
            >
              <ZoomOut size={14} />
            </button>
            <button
              className="btn-secondary"
              style={{ padding: '0.25rem 0.5rem', minWidth: '46px', fontSize: '0.75rem', fontWeight: 600 }}
              title="Reset Zoom to 100%"
              onClick={handleResetZoom}
            >
              {Math.round(zoom * 100)}%
            </button>
            <button
              className="btn-secondary"
              style={{ padding: '0.25rem 0.45rem' }}
              title="Zoom in"
              onClick={handleZoomIn}
              disabled={zoom >= 2.5}
            >
              <ZoomIn size={14} />
            </button>
            <button
              className="btn-secondary"
              style={{ padding: '0.25rem 0.45rem' }}
              title="Open full view zoom lightbox"
              onClick={() => setIsLightboxOpen(true)}
            >
              <Maximize2 size={14} />
            </button>
          </div>

          {/* Limited Pagination: strictly 1 to maxPages */}
          <button
            className="btn-secondary"
            style={{ padding: '0.25rem 0.45rem' }}
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            title="Previous Page"
          >
            <ChevronLeft size={16} />
          </button>

          <span style={{ fontWeight: 500, minWidth: '70px', textAlign: 'center' }}>
            Page {currentPage} of {maxPages}
          </span>

          <button
            className="btn-secondary"
            style={{ padding: '0.25rem 0.45rem' }}
            disabled={currentPage >= maxPages}
            onClick={() => setCurrentPage((p) => Math.min(maxPages, p + 1))}
            title="Next Page"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {selectedFinding && !hasReliableLocation && (
        <div className="preview-limitation-banner">
          <AlertCircle size={15} style={{ verticalAlign: 'middle', marginRight: '0.35rem' }} />
          <strong>Exact location not highlighted:</strong>{' '}
          {selectedFinding.is_missing_from_artwork
            ? 'This item was not found on the packaging artwork.'
            : selectedFinding.artwork_source?.page && selectedFinding.artwork_source.page !== currentPage
            ? `Located on Page ${selectedFinding.artwork_source.page}. Use page navigation above to view.`
            : 'Native PDF coordinates could not be isolated reliably.'}
        </div>
      )}

      {/* Main Artwork Preview Display */}
      <div
        ref={previewContainerRef}
        className="pdf-display-container"
        style={{
          maxHeight: '560px',
          overflow: 'auto',
          justifyContent: zoom > 1 ? 'flex-start' : 'center',
          alignItems: zoom > 1 ? 'flex-start' : 'center',
          cursor: zoom > 1 ? 'grab' : 'zoom-in',
          userSelect: 'none'
        }}
        onClick={handleImageClick}
        title="Click to toggle 150% zoom, or use toolbar zoom controls"
      >
        <div
          className="pdf-page-image-wrapper"
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: 'top left',
            transition: 'transform 0.2s ease-out'
          }}
        >
          <img
            ref={imgRef}
            src={imageUrl}
            alt={`Artwork Page ${currentPage}`}
            className="pdf-page-image"
            onLoad={handleImageLoad}
          />
          {highlightStyle && (
            <div
              className="pdf-highlight-overlay"
              style={highlightStyle}
              title={`Discrepancy: ${selectedFinding.field_name}`}
            />
          )}
        </div>
      </div>

      {/* Fullscreen / Lightbox Modal for In-depth Inspection */}
      {isLightboxOpen && (
        <div
          className="modal-backdrop"
          style={{ zIndex: 1000, background: 'rgba(15, 23, 42, 0.9)' }}
          onClick={() => setIsLightboxOpen(false)}
        >
          <div
            style={{
              position: 'relative',
              maxWidth: '94vw',
              maxHeight: '94vh',
              width: '100%',
              height: '100%',
              display: 'flex',
              flexDirection: 'column',
              background: '#0f172a',
              borderRadius: '12px',
              padding: '1rem',
              overflow: 'hidden'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Toolbar */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingBottom: '0.75rem',
                borderBottom: '1px solid #334155',
                color: 'white'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <strong style={{ fontSize: '1.1rem' }}>Artwork Inspection Lightbox</strong>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: '#94a3b8' }}>
                  <button
                    className="btn-secondary"
                    style={{ background: '#1e293b', color: 'white', borderColor: '#475569', padding: '0.25rem' }}
                    disabled={currentPage <= 1}
                    onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                    title="Previous Page"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <span style={{ fontSize: '0.85rem', minWidth: '90px', textAlign: 'center' }}>
                    Page {currentPage} of {maxPages}
                  </span>
                  <button
                    className="btn-secondary"
                    style={{ background: '#1e293b', color: 'white', borderColor: '#475569', padding: '0.25rem' }}
                    disabled={currentPage >= maxPages}
                    onClick={() => setCurrentPage((page) => Math.min(maxPages, page + 1))}
                    title="Next Page"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
                {selectedFinding && (
                  <span style={{ fontSize: '0.8rem', background: '#334155', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
                    Highlight: {selectedFinding.field_name}
                  </span>
                )}
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <button
                  className="btn-secondary"
                  style={{ background: '#1e293b', color: 'white', borderColor: '#475569', padding: '0.3rem 0.6rem' }}
                  onClick={() => setLightboxZoom((z) => Math.max(z - 0.25, 0.75))}
                >
                  <ZoomOut size={16} />
                </button>
                <span style={{ fontSize: '0.85rem', minWidth: '45px', textAlign: 'center' }}>
                  {Math.round(lightboxZoom * 100)}%
                </span>
                <button
                  className="btn-secondary"
                  style={{ background: '#1e293b', color: 'white', borderColor: '#475569', padding: '0.3rem 0.6rem' }}
                  onClick={() => setLightboxZoom((z) => Math.min(z + 0.25, 3.5))}
                >
                  <ZoomIn size={16} />
                </button>
                <button
                  className="btn-secondary"
                  style={{ background: '#1e293b', color: 'white', borderColor: '#475569', padding: '0.3rem 0.6rem' }}
                  onClick={() => setLightboxZoom(1)}
                  title="Reset Zoom"
                >
                  <RotateCcw size={16} />
                </button>
                <button
                  className="btn-secondary"
                  style={{ background: '#ef4444', color: 'white', borderColor: '#ef4444', padding: '0.3rem 0.6rem', marginLeft: '0.5rem' }}
                  onClick={() => setIsLightboxOpen(false)}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Image Area with Pan/Scroll */}
            <div
              ref={lightboxContainerRef}
              style={{
                flex: 1,
                overflow: 'auto',
                display: 'flex',
                justifyContent: 'flex-start',
                alignItems: 'flex-start',
                padding: '2rem',
                cursor: lightboxZoom > 1 ? 'grab' : 'default'
              }}
            >
              <div
                style={{
                  position: 'relative',
                  display: 'inline-block',
                  transform: `scale(${lightboxZoom})`,
                  transformOrigin: 'top left',
                  transition: 'transform 0.15s ease-out',
                  boxShadow: '0 8px 30px rgba(0, 0, 0, 0.6)',
                  background: 'white'
                }}
              >
                <img
                  src={imageUrl}
                  alt={`Artwork Page ${currentPage} Full Inspection`}
                  style={{ display: 'block', maxWidth: '850px' }}
                />
                {highlightStyle && (
                  <div
                    className="pdf-highlight-overlay"
                    style={highlightStyle}
                    title={`Discrepancy: ${selectedFinding.field_name}`}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
