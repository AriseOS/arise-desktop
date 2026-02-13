import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import Icon from '../components/Icons';

const BackendErrorPage = ({ onRetry }) => {
    const { t } = useTranslation();
    const [logs, setLogs] = useState([]);
    const [logPath, setLogPath] = useState('');
    const [loading, setLoading] = useState(true);
    const [expanded, setExpanded] = useState(false);
    const [retrying, setRetrying] = useState(false);

    useEffect(() => {
        loadLogs();
    }, []);

    const loadLogs = async () => {
        setLoading(true);
        try {
            const result = await window.electronAPI.readDaemonLogs(50);
            if (result.success) {
                setLogs(result.logs || []);
                setLogPath(result.path || '');
            } else {
                setLogs([`Error: ${result.error}`]);
                setLogPath(result.path || '');
            }
        } catch (error) {
            console.error('[BackendErrorPage] Failed to read logs:', error);
            setLogs([`Failed to read logs: ${error.message}`]);
        } finally {
            setLoading(false);
        }
    };

    const handleRetry = async () => {
        setRetrying(true);
        try {
            await onRetry?.();
        } finally {
            setRetrying(false);
        }
    };

    const formatLogLine = (line) => {
        try {
            const parsed = JSON.parse(line);
            const level = parsed.level || 'INFO';
            const timestamp = parsed.timestamp ? new Date(parsed.timestamp).toLocaleTimeString() : '';
            const message = parsed.message || line;
            const module = parsed.module || '';

            return {
                level,
                timestamp,
                message,
                module,
                isError: level === 'ERROR' || level === 'WARNING',
                raw: line
            };
        } catch {
            return {
                level: 'INFO',
                timestamp: '',
                message: line,
                module: '',
                isError: false,
                raw: line
            };
        }
    };

    const getLevelColor = (level) => {
        switch (level) {
            case 'ERROR': return 'var(--status-error-text)';
            case 'WARNING': return 'var(--status-warning-text)';
            case 'DEBUG': return 'var(--text-tertiary)';
            default: return 'var(--text-secondary)';
        }
    };

    return (
        <div className="page backend-error-page flex-center" style={{ height: '100vh', background: 'var(--bg-primary)', padding: '20px' }}>
            <div className="card" style={{ padding: '32px', maxWidth: '700px', width: '100%' }}>
                <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                    <div style={{
                        width: '64px',
                        height: '64px',
                        borderRadius: '50%',
                        backgroundColor: 'var(--status-error-bg)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        margin: '0 auto 16px'
                    }}>
                        <Icon name="alert" size={32} style={{ color: 'var(--status-error-text)' }} />
                    </div>
                    <h1 style={{ fontSize: '24px', marginBottom: '8px', color: 'var(--text-primary)' }}>
                        {t('backendError.title')}
                    </h1>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
                        {t('backendError.description')}
                    </p>
                </div>

                <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginBottom: '24px' }}>
                    <button
                        className="btn btn-primary"
                        onClick={handleRetry}
                        disabled={retrying}
                        style={{ padding: '12px 24px', minWidth: '140px' }}
                    >
                        {retrying ? (
                            <>
                                <div className="loading-spinner-sm" style={{ width: '16px', height: '16px' }}></div>
                                <span>{t('backendError.retrying')}</span>
                            </>
                        ) : (
                            <>
                                <Icon name="refresh" size={18} />
                                <span>{t('backendError.retry')}</span>
                            </>
                        )}
                    </button>
                </div>

                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '20px' }}>
                    <button
                        onClick={() => setExpanded(!expanded)}
                        style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: 'var(--text-secondary)',
                            fontSize: '14px',
                            padding: '8px 0',
                            width: '100%'
                        }}
                    >
                        <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={16} />
                        <span>{t('backendError.viewLogs')}</span>
                        {logPath && (
                            <span style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--text-tertiary)' }}>
                                {logPath}
                            </span>
                        )}
                    </button>

                    {expanded && (
                        <div style={{ marginTop: '12px' }}>
                            <div style={{
                                display: 'flex',
                                justifyContent: 'flex-end',
                                marginBottom: '8px'
                            }}>
                                <button
                                    className="btn btn-secondary"
                                    onClick={loadLogs}
                                    disabled={loading}
                                    style={{ padding: '6px 12px', fontSize: '12px' }}
                                >
                                    <Icon name="refresh" size={14} />
                                    <span>{t('backendError.refreshLogs')}</span>
                                </button>
                            </div>

                            <div style={{
                                backgroundColor: 'var(--bg-app)',
                                borderRadius: '8px',
                                padding: '12px',
                                maxHeight: '300px',
                                overflowY: 'auto',
                                fontFamily: 'monospace',
                                fontSize: '12px',
                                lineHeight: '1.6'
                            }}>
                                {loading ? (
                                    <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)' }}>
                                        {t('common.loading')}
                                    </div>
                                ) : logs.length === 0 ? (
                                    <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)' }}>
                                        {t('backendError.noLogs')}
                                    </div>
                                ) : (
                                    logs.map((line, index) => {
                                        const formatted = formatLogLine(line);
                                        return (
                                            <div
                                                key={index}
                                                style={{
                                                    padding: '4px 0',
                                                    borderBottom: index < logs.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                                                    color: getLevelColor(formatted.level)
                                                }}
                                            >
                                                {formatted.timestamp && (
                                                    <span style={{ color: 'var(--text-tertiary)', marginRight: '8px' }}>
                                                        [{formatted.timestamp}]
                                                    </span>
                                                )}
                                                <span style={{
                                                    fontWeight: formatted.isError ? 600 : 400,
                                                    color: getLevelColor(formatted.level),
                                                    marginRight: '8px'
                                                }}>
                                                    [{formatted.level}]
                                                </span>
                                                {formatted.module && (
                                                    <span style={{ color: 'var(--text-tertiary)', marginRight: '8px' }}>
                                                        {formatted.module}:
                                                    </span>
                                                )}
                                                <span style={{ color: formatted.isError ? getLevelColor(formatted.level) : 'var(--text-primary)' }}>
                                                    {formatted.message}
                                                </span>
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    )}
                </div>

                <div style={{ marginTop: '20px', textAlign: 'center' }}>
                    <p style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
                        {t('backendError.helpHint')}
                    </p>
                </div>
            </div>
        </div>
    );
};

export default BackendErrorPage;
