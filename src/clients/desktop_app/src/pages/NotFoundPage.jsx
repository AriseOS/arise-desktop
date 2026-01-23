/**
 * NotFoundPage Component
 *
 * 404 page displayed when a route is not found.
 *
 * Ported from Eigent's NotFound page.
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';
import Icon from '../components/Icons';

function NotFoundPage() {
  const navigate = useNavigate();

  const handleGoHome = () => {
    navigate('/');
  };

  const handleGoBack = () => {
    navigate(-1);
  };

  return (
    <div className="not-found-page">
      <div className="not-found-content">
        <div className="not-found-icon">
          <Icon name="alertTriangle" size={64} />
        </div>

        <h1 className="not-found-title">404</h1>
        <p className="not-found-subtitle">Page Not Found</p>
        <p className="not-found-description">
          The page you are looking for might have been removed, had its name changed,
          or is temporarily unavailable.
        </p>

        <div className="not-found-actions">
          <button className="btn btn-primary" onClick={handleGoHome}>
            <Icon name="home" size={16} />
            Go Home
          </button>
          <button className="btn btn-secondary" onClick={handleGoBack}>
            <Icon name="arrowLeft" size={16} />
            Go Back
          </button>
        </div>
      </div>

      <style>{`
        .not-found-page {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          padding: 20px;
          background: var(--bg-app, #f5f5f5);
        }

        .not-found-content {
          text-align: center;
          max-width: 400px;
        }

        .not-found-icon {
          color: var(--text-tertiary, #999);
          margin-bottom: 24px;
        }

        .not-found-title {
          font-size: 72px;
          font-weight: 700;
          color: var(--text-primary, #1a1a1a);
          margin: 0;
          line-height: 1;
        }

        .not-found-subtitle {
          font-size: 24px;
          font-weight: 600;
          color: var(--text-secondary, #666);
          margin: 8px 0 16px;
        }

        .not-found-description {
          font-size: 14px;
          color: var(--text-tertiary, #999);
          margin: 0 0 32px;
          line-height: 1.5;
        }

        .not-found-actions {
          display: flex;
          gap: 12px;
          justify-content: center;
        }

        .not-found-actions .btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 20px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .not-found-actions .btn-primary {
          background: var(--brand-primary, #6366f1);
          color: white;
          border: none;
        }

        .not-found-actions .btn-primary:hover {
          background: var(--brand-hover, #4f46e5);
        }

        .not-found-actions .btn-secondary {
          background: var(--bg-primary, #fff);
          color: var(--text-primary, #1a1a1a);
          border: 1px solid var(--border-color, #e5e5e5);
        }

        .not-found-actions .btn-secondary:hover {
          background: var(--bg-hover, #f5f5f5);
        }
      `}</style>
    </div>
  );
}

export default NotFoundPage;
