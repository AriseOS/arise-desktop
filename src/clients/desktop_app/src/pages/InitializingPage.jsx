import React from 'react';
import { useTranslation } from 'react-i18next';
import '../styles/SetupPage.css'; // Reusing setup styles for consistency

const InitializingPage = () => {
    const { t } = useTranslation();
    return (
        <div className="page setup-page flex-center fade-in">
            <div className="setup-container card">
                <div className="setup-header">
                    <div className="logo-icon-lg">Ami</div>
                    <h1 className="setup-title">{t('initializing.welcome')}</h1>
                    <p className="setup-subtitle">{t('initializing.title')}</p>
                </div>

                <div className="setup-content flex-col center-content" style={{ padding: '40px 0' }}>
                    <div className="loading-spinner-lg"></div>
                    <p style={{ marginTop: '24px', color: 'var(--text-secondary)' }}>
                        {t('initializing.connecting')}
                    </p>
                </div>

                <div className="setup-footer">
                    <p>{t('initializing.wait')}</p>
                </div>
            </div>
        </div>
    );
};

export default InitializingPage;
