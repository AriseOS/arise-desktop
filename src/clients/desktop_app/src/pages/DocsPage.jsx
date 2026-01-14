import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';
import '../styles/DocsPage.css';

const DOCS_URL = 'https://docs.ariseos.com';

function DocsPage({ onNavigate }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);

  return (
    <div className="page docs-page">
      <div className="docs-header">
        <button className="back-button" onClick={() => onNavigate('main')}>
          <Icon icon="arrowLeft" size={16} /> {t('docs.back')}
        </button>
        <h1 className="docs-title">{t('docs.title')}</h1>
        <div className="docs-header-actions">
          <a
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary btn-sm"
          >
            {t('docs.openInBrowser')}
          </a>
        </div>
      </div>

      <div className="docs-iframe-container">
        {loading && (
          <div className="docs-loading">
            <div className="loading-spinner" />
            <p>{t('docs.loading')}</p>
          </div>
        )}
        <iframe
          src={DOCS_URL}
          title="Documentation"
          className="docs-iframe"
          onLoad={() => setLoading(false)}
        />
      </div>
    </div>
  );
}

export default DocsPage;
