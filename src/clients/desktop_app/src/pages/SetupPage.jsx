import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../utils/api";

function SetupPage({ onSetupComplete }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState("checking");
  const [message, setMessage] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [browserInfo, setBrowserInfo] = useState(null);

  useEffect(() => {
    setMessage(t('setup.checking')); // Set initial message
    checkBrowserStatus();
  }, [t]);

  const checkBrowserStatus = async () => {
    try {
      // Check browser availability (always true with Electron)
      const browserInfo = await window.electronAPI.checkBrowserInstalled();
      setBrowserInfo(browserInfo);

      console.log("Browser check result:", browserInfo);

      if (browserInfo.available) {
        // Browser is available (Chrome or Playwright Chromium)
        setStatus("ready");
        setMessage(t('setup.ready', { browser: browserInfo.browser_type }));
        setProgress(100);
        setTimeout(() => onSetupComplete(), 1000);
      } else {
        // No browser found, show installation option
        setStatus("pending");
        setMessage(t('setup.notFound'));
        setProgress(0);
      }
    } catch (err) {
      console.error("Failed to check browser:", err);
      setError(t('setup.checkFailed'));
    }
  };

  const retryCheck = () => {
    setError(null);
    setStatus("checking");
    setMessage(t('setup.checking'));
    checkBrowserStatus();
  };

  return (
    <div className="setup-page">
      <div className="setup-container">
        <div className="setup-icon">
          {status === "ready" ? (
            <div className="check-icon">✓</div>
          ) : status === "error" ? (
            <div className="error-icon">✗</div>
          ) : (
            <div className="spinner"></div>
          )}
        </div>

        <h1>{t('setup.title')}</h1>

        {error ? (
          <div className="setup-error">
            <p className="error-message">{error}</p>
            <button onClick={retryCheck} className="retry-button">
              {t('setup.retry')}
            </button>
          </div>
        ) : (
          <>
            <p className="setup-message">{message}</p>

            {status === "pending" && (
              <div className="setup-actions">
                <p className="setup-note">
                  {t('setup.installChrome')}
                  <br />
                  <a href="https://www.google.com/chrome/" target="_blank" rel="noopener noreferrer">
                    https://www.google.com/chrome/
                  </a>
                </p>
                <button onClick={retryCheck} className="retry-button">
                  {t('setup.installedRetry')}
                </button>
              </div>
            )}

            {status === "ready" && (
              <p className="setup-success">{t('setup.complete')}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default SetupPage;
