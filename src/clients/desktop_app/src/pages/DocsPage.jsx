import { useState } from 'react';
import Icon from '../components/Icons';
import '../styles/DocsPage.css';

const DOCS_URL = 'https://docs.ariseos.com';

function DocsPage({ language = 'en', onNavigate }) {
  const [loading, setLoading] = useState(true);

  const headerTitle = language === 'zh' ? '使用手册' : 'Help & User Guide';
  const backLabel = language === 'zh' ? '返回' : 'Back';

  return (
    <div className="page docs-page">
      <div className="docs-header">
        <button className="back-button" onClick={() => onNavigate('main')}>
          <Icon icon="arrowLeft" size={16} /> {backLabel}
        </button>
        <h1 className="docs-title">{headerTitle}</h1>
        <div className="docs-header-actions">
          <a
            href={DOCS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-secondary btn-sm"
          >
            {language === 'zh' ? '在浏览器中打开' : 'Open in Browser'}
          </a>
        </div>
      </div>

      <div className="docs-iframe-container">
        {loading && (
          <div className="docs-loading">
            <div className="loading-spinner" />
            <p>{language === 'zh' ? '正在加载文档...' : 'Loading documentation...'}</p>
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
