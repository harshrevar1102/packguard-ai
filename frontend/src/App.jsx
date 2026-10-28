import React, { useState } from 'react';
import Home from './components/Home';
import ExistingProducts from './components/ExistingProducts';
import NewProductForm from './components/NewProductForm';
import ProductDetail from './components/ProductDetail';
import AnalysisResults from './components/AnalysisResults';
import './App.css';

export default function App() {
  const [currentView, setCurrentView] = useState('home'); // 'home' | 'existing' | 'new' | 'product_detail' | 'results'
  const [selectedProductId, setSelectedProductId] = useState(null);
  const [prefilledProductName, setPrefilledProductName] = useState('');
  const [currentAnalysis, setCurrentAnalysis] = useState(null);

  // Navigation handlers
  const handleNavigate = (view) => {
    setCurrentView(view);
  };

  const handleSelectProduct = (productId) => {
    setSelectedProductId(productId);
    setCurrentView('product_detail');
  };

  const handleStartNewAnalysisForProduct = (productName) => {
    setPrefilledProductName(productName);
    setCurrentView('new');
  };

  const handleAnalysisComplete = (analysis) => {
    setCurrentAnalysis(analysis);
    setCurrentView('results');
  };

  const handleSelectHistoricalAnalysis = (analysis) => {
    setCurrentAnalysis(analysis);
    setCurrentView('results');
  };

  const handleBackToProduct = (productId) => {
    setSelectedProductId(productId);
    setCurrentView('product_detail');
  };

  return (
    <div className="app-container">
      {/* Brand Header */}
      <header className="app-header">
        <div className="header-brand" onClick={() => setCurrentView('home')}>
          <div className="brand-badge">PG</div>
          <div>
            <div className="brand-title">PackGuard AI</div>
            <div className="header-subtitle">Packaging Artwork & Specification Verification</div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="main-content">
        {currentView === 'home' && (
          <Home onNavigate={handleNavigate} />
        )}

        {currentView === 'existing' && (
          <ExistingProducts
            onNavigate={handleNavigate}
            onSelectProduct={handleSelectProduct}
          />
        )}

        {currentView === 'new' && (
          <NewProductForm
            onNavigate={handleNavigate}
            onAnalysisComplete={handleAnalysisComplete}
            initialProductName={prefilledProductName}
          />
        )}

        {currentView === 'product_detail' && selectedProductId && (
          <ProductDetail
            productId={selectedProductId}
            onNavigate={handleNavigate}
            onSelectAnalysis={handleSelectHistoricalAnalysis}
            onStartNewAnalysisForProduct={handleStartNewAnalysisForProduct}
          />
        )}

        {currentView === 'results' && currentAnalysis && (
          <AnalysisResults
            analysis={currentAnalysis}
            onNavigate={handleNavigate}
            onBackToProduct={handleBackToProduct}
          />
        )}
      </main>
    </div>
  );
}
