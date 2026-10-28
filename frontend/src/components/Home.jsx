import React from 'react';
import { FolderOpen, PlusCircle, ArrowRight } from 'lucide-react';

export default function Home({ onNavigate }) {
  return (
    <div className="home-container">
      <h1 className="home-headline">PackGuard AI</h1>
      <p className="home-subheadline">
        Packaging Artwork & Specification Verification Engine
      </p>

      <div className="home-options-grid">
        <div 
          className="home-card" 
          onClick={() => onNavigate('existing')}
          role="button"
          tabIndex={0}
        >
          <div>
            <div className="card-icon-wrapper secondary">
              <FolderOpen size={26} />
            </div>
            <h3>Analyse Existing Product</h3>
            <p>
              Access previously saved products, review historical document analyses, 
              compare version evolutions, or run a new verification check.
            </p>
          </div>
          <div className="card-action-btn">
            Browse Products <ArrowRight size={18} />
          </div>
        </div>

        <div 
          className="home-card" 
          onClick={() => onNavigate('new')}
          role="button"
          tabIndex={0}
        >
          <div>
            <div className="card-icon-wrapper primary">
              <PlusCircle size={26} />
            </div>
            <h3>Analyse New Product</h3>
            <p>
              Upload specification spreadsheets and packaging artwork PDF to detect 
              inconsistencies, missing declarations, and verify packaging compliance.
            </p>
          </div>
          <div className="card-action-btn">
            Start New Analysis <ArrowRight size={18} />
          </div>
        </div>
      </div>
    </div>
  );
}
