import React from 'react';
import '../styles/SetupPage.css'; // Reusing setup styles for consistency

const InitializingPage = () => {
    return (
        <div className="page setup-page flex-center fade-in">
            <div className="setup-container card">
                <div className="setup-header">
                    <div className="logo-icon-lg">Ami</div>
                    <h1 className="setup-title">Welcome back</h1>
                    <p className="setup-subtitle">Initializing application services...</p>
                </div>

                <div className="setup-content flex-col center-content" style={{ padding: '40px 0' }}>
                    <div className="loading-spinner-lg"></div>
                    <p style={{ marginTop: '24px', color: 'var(--text-secondary)' }}>
                        Connecting to local daemon...
                    </p>
                </div>

                <div className="setup-footer">
                    <p>Please wait while we prepare your workspace.</p>
                </div>
            </div>
        </div>
    );
};

export default InitializingPage;
