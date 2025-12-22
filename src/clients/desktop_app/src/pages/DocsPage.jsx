import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import Icon from '../components/Icons';
import { getTopics, loadDoc } from '../docs/user_guide/docsLoader';
import '../styles/DocsPage.css';

function DocsPage({ language = 'en', onLanguageChange, onNavigate, showStatus, topicId }) {
  const [currentTopicId, setCurrentTopicId] = useState(topicId || 'overview-getting-started');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const topics = getTopics(language);

  useEffect(() => {
    if (!topicId) return;
    setCurrentTopicId(topicId);
  }, [topicId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    loadDoc(currentTopicId, language)
      .then((md) => {
        if (cancelled) return;
        setContent(md || '');
      })
      .catch((err) => {
        console.error('[DocsPage] Failed to load docs:', err);
        if (cancelled) return;
        setError('Failed to load documentation.');
        if (showStatus) {
          showStatus(`Failed to load docs: ${err.message}`, 'error');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [currentTopicId, language]);

  const handleLanguageChange = (lang) => {
    if (onLanguageChange) {
      onLanguageChange(lang);
    }
  };

  const headerTitle = language === 'zh' ? '使用手册' : 'Help & User Guide';
  const backLabel = language === 'zh' ? '返回' : 'Back';
  const languageLabel = language === 'zh' ? '语言' : 'Language';

  return (
    <div className="page docs-page">
      <div className="docs-header">
        <button className="back-button" onClick={() => onNavigate('main')}>
          <Icon icon="arrowLeft" size={16} /> {backLabel}
        </button>
        <h1 className="docs-title">{headerTitle}</h1>
        <div className="docs-header-actions">
          <span className="language-label">{languageLabel}:</span>
          <div className="language-toggle">
            <button
              type="button"
              className={`lang-btn ${language === 'en' ? 'active' : ''}`}
              onClick={() => handleLanguageChange('en')}
            >
              EN
            </button>
            <button
              type="button"
              className={`lang-btn ${language === 'zh' ? 'active' : ''}`}
              onClick={() => handleLanguageChange('zh')}
            >
              中文
            </button>
          </div>
        </div>
      </div>

      <div className="docs-content">
        <aside className="docs-sidebar">
          <ul className="docs-topic-list">
            {topics.map((topic) => (
              <li key={topic.id}>
                <button
                  type="button"
                  className={`topic-item ${currentTopicId === topic.id ? 'active' : ''}`}
                  onClick={() => setCurrentTopicId(topic.id)}
                >
                  {topic.title}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="docs-main">
          {loading && (
            <div className="docs-loading">
              <div className="loading-spinner" />
              <p>{language === 'zh' ? '正在加载文档...' : 'Loading documentation...'}</p>
            </div>
          )}

          {!loading && error && (
            <div className="docs-error">
              <p>{language === 'zh' ? '加载文档失败。' : 'Failed to load documentation.'}</p>
            </div>
          )}

          {!loading && !error && (
            <article className="docs-article">
              <ReactMarkdown>{content}</ReactMarkdown>
            </article>
          )}
        </main>
      </div>
    </div>
  );
}

export default DocsPage;
