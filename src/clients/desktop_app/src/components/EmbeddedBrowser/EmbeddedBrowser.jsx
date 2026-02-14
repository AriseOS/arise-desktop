/**
 * EmbeddedBrowser — renders a native Electron WebContentsView at calculated bounds.
 *
 * WebContentsView is NOT a DOM element — it's a native overlay positioned at absolute
 * pixel coordinates. This component reserves DOM space and reports bounds to Electron
 * via IPC so the native view aligns with the React layout.
 *
 * Props:
 *   viewId: string        — "0"-"7" (Electron pool slot)
 *   visible: boolean      — show/hide native view
 *   interactive: boolean  — true=user clickable, false=view-only
 *   showControls: boolean — URL bar + nav buttons
 *   initialUrl?: string   — navigate on mount
 *   onClose?: () => void  — close button callback
 *   onUrlChange?: (url) => void — URL change callback
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import Icon from '../Icons';
import './EmbeddedBrowser.css';

export default function EmbeddedBrowser({
  viewId,
  visible = true,
  interactive = true,
  showControls = true,
  initialUrl = '',
  onClose,
  onUrlChange,
}) {
  const containerRef = useRef(null);
  const [currentUrl, setCurrentUrl] = useState(initialUrl || '');
  const [inputUrl, setInputUrl] = useState(initialUrl || '');
  const [isLoading, setIsLoading] = useState(false);
  const boundsRef = useRef(null);
  // Guard: prevent showWebview IPC calls after unmount or when hidden
  const activeRef = useRef(false);

  // Send bounds to Electron to position the native WebContentsView
  const updateBounds = useCallback(() => {
    // Check both component-level and global guards. The global flag is set
    // synchronously by App.navigate() before React commits the unmount.
    if (!activeRef.current || window.__amiWebviewsHidden || !containerRef.current || !visible || !viewId) return;

    const rect = containerRef.current.getBoundingClientRect();
    // Reject degenerate bounds (element not laid out yet or off-screen)
    if (rect.width < 10 || rect.height < 10) return;

    const bounds = {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
    };

    // Skip if bounds haven't changed
    const prev = boundsRef.current;
    if (prev && prev.x === bounds.x && prev.y === bounds.y
        && prev.width === bounds.width && prev.height === bounds.height) {
      return;
    }
    boundsRef.current = bounds;

    window.electronAPI?.showWebview(viewId, bounds);
  }, [viewId, visible]);

  // Show/hide native view based on visible prop
  useEffect(() => {
    if (!viewId) return;

    if (visible) {
      activeRef.current = true;
      window.__amiWebviewsHidden = false;
      // Double-rAF ensures layout is committed before measuring bounds.
      // Unlike setTimeout(50ms), rAF callbacks fire within the same frame.
      // The cancelled flag + global guard prevent stale showWebview calls.
      let cancelled = false;
      const raf1 = requestAnimationFrame(() => {
        if (cancelled) return;
        requestAnimationFrame(() => {
          if (!cancelled) updateBounds();
        });
      });
      return () => {
        cancelled = true;
        cancelAnimationFrame(raf1);
      };
    } else {
      activeRef.current = false;
      window.electronAPI?.hideWebview(viewId);
      boundsRef.current = null;
    }
  }, [viewId, visible, updateBounds]);

  // ResizeObserver to track container size changes
  useEffect(() => {
    if (!containerRef.current || !visible) return;

    let debounceTimer = null;
    const debouncedUpdate = () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(updateBounds, 100);
    };

    const observer = new ResizeObserver(debouncedUpdate);
    observer.observe(containerRef.current);

    // Also update on window resize/scroll
    window.addEventListener('resize', debouncedUpdate);
    window.addEventListener('scroll', debouncedUpdate, true);

    return () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      observer.disconnect();
      window.removeEventListener('resize', debouncedUpdate);
      window.removeEventListener('scroll', debouncedUpdate, true);
    };
  }, [visible, updateBounds]);

  // Handle viewId prop changes without remounting
  const prevViewIdRef = useRef(viewId);
  useEffect(() => {
    if (prevViewIdRef.current !== viewId) {
      // Hide previous view
      window.electronAPI?.hideWebview(prevViewIdRef.current);
      boundsRef.current = null; // Force re-measure
      prevViewIdRef.current = viewId;
      // Fetch current URL for new view
      window.electronAPI?.getWebviewUrl(viewId).then((url) => {
        if (url) {
          setCurrentUrl(url);
          setInputUrl(url);
        }
      });
    }
  }, [viewId]);

  // Navigate to initial URL on mount only (not on viewId changes)
  const initialUrlNavigatedRef = useRef(false);
  useEffect(() => {
    if (!viewId || !initialUrl || !visible) return;
    if (initialUrlNavigatedRef.current) return;
    initialUrlNavigatedRef.current = true;
    window.electronAPI?.navigateWebview(viewId, initialUrl);
  }, [viewId, initialUrl, visible]);

  // Listen for URL updates from Electron
  useEffect(() => {
    if (!viewId) return;

    const cleanup = window.electronAPI?.onUrlUpdated((updatedViewId, url) => {
      if (updatedViewId === viewId) {
        setCurrentUrl(url);
        setInputUrl(url);
        setIsLoading(false);
        onUrlChange?.(url);
      }
    });

    return () => cleanup?.();
  }, [viewId, onUrlChange]);

  // Cleanup: hide view on unmount
  useEffect(() => {
    return () => {
      activeRef.current = false;
      if (viewId) {
        window.electronAPI?.hideWebview(viewId);
      }
    };
  }, [viewId]);

  // URL bar submit
  const handleUrlSubmit = (e) => {
    e.preventDefault();
    if (!inputUrl.trim() || !viewId) return;

    let url = inputUrl.trim();
    // Auto-add https:// if no protocol
    if (!/^https?:\/\//i.test(url) && !/^about:/i.test(url)) {
      url = `https://${url}`;
    }

    setIsLoading(true);
    window.electronAPI?.navigateWebview(viewId, url);
  };

  const handleGoBack = () => window.electronAPI?.webviewGoBack(viewId);
  const handleGoForward = () => window.electronAPI?.webviewGoForward(viewId);
  const handleReload = () => {
    setIsLoading(true);
    window.electronAPI?.webviewReload(viewId);
  };

  return (
    <div className="embedded-browser" data-interactive={interactive}>
      {showControls && (
        <div className="embedded-browser-controls">
          <div className="browser-nav-buttons">
            <button className="browser-nav-btn" onClick={handleGoBack} title="Back">
              <Icon name="chevronLeft" size={16} />
            </button>
            <button className="browser-nav-btn" onClick={handleGoForward} title="Forward">
              <Icon name="chevronRight" size={16} />
            </button>
            <button className="browser-nav-btn" onClick={handleReload} title="Reload">
              <Icon name={isLoading ? 'x' : 'refresh'} size={14} />
            </button>
          </div>

          <form className="browser-url-form" onSubmit={handleUrlSubmit}>
            <input
              type="text"
              className="browser-url-input"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="Enter URL..."
              spellCheck={false}
            />
          </form>

          {onClose && (
            <button className="browser-close-btn" onClick={onClose} title="Close">
              <Icon name="x" size={16} />
            </button>
          )}
        </div>
      )}

      {/* Container that reserves DOM space for the native WebContentsView.
          pointerEvents='none' because the native view sits on top at the same
          pixel coordinates — this div is just a layout placeholder. */}
      <div
        ref={containerRef}
        className="embedded-browser-viewport"
        style={{ pointerEvents: 'none' }}
      />

      {/* Transparent overlay to block interaction when not interactive */}
      {!interactive && (
        <div className="embedded-browser-shield" />
      )}
    </div>
  );
}
