import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { api } from "../utils/api";

function SetupPage({ onSetupComplete }) {
  const [status, setStatus] = useState("checking");
  const [message, setMessage] = useState("Checking browser installation...");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [browserInfo, setBrowserInfo] = useState(null);

  useEffect(() => {
    checkBrowserStatus();
  }, []);

  const checkBrowserStatus = async () => {
    try {
      // Use Tauri command to check browser (no dependency on daemon)
      const browserInfo = await invoke("check_browser_installed");
      setBrowserInfo(browserInfo);

      console.log("Browser check result:", browserInfo);

      if (browserInfo.available) {
        // Browser is available (Chrome or Playwright Chromium)
        setStatus("ready");
        setMessage(`Found ${browserInfo.browser_type}, ready to use!`);
        setProgress(100);
        setTimeout(() => onSetupComplete(), 1000);
      } else {
        // No browser found, show installation option
        setStatus("pending");
        setMessage("No browser found. Please install Google Chrome or click below to install Chromium.");
        setProgress(0);
      }
    } catch (err) {
      console.error("Failed to check browser:", err);
      setError("Failed to check browser installation. Please restart the app.");
    }
  };

  const retryCheck = () => {
    setError(null);
    setStatus("checking");
    setMessage("Checking browser installation...");
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

        <h1>Welcome to Ami</h1>

        {error ? (
          <div className="setup-error">
            <p className="error-message">{error}</p>
            <button onClick={retryCheck} className="retry-button">
              Retry
            </button>
          </div>
        ) : (
          <>
            <p className="setup-message">{message}</p>

            {status === "pending" && (
              <div className="setup-actions">
                <p className="setup-note">
                  Please download and install Google Chrome from:
                  <br />
                  <a href="https://www.google.com/chrome/" target="_blank" rel="noopener noreferrer">
                    https://www.google.com/chrome/
                  </a>
                </p>
                <button onClick={retryCheck} className="retry-button">
                  I've installed Chrome - Retry Check
                </button>
              </div>
            )}

            {status === "ready" && (
              <p className="setup-success">Setup complete! Launching app...</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default SetupPage;
