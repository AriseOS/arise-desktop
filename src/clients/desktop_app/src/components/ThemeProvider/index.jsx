/**
 * ThemeProvider Component
 *
 * Manages application theme/appearance by setting data-theme attribute on document root.
 * Supports light, dark, transparent, and system themes.
 *
 * Ported from Eigent's ThemeProvider.tsx.
 */

import { useEffect, useState } from 'react';
import { useStore } from 'zustand';
import settingsStore from '../../store/settingsStore';

/**
 * Hook to get system color scheme preference
 */
function useSystemTheme() {
  const [systemTheme, setSystemTheme] = useState(() => {
    if (typeof window !== 'undefined' && window.matchMedia) {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    return 'light';
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = (e) => {
      setSystemTheme(e.matches ? 'dark' : 'light');
    };

    // Modern browsers
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }
    // Legacy Safari
    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  return systemTheme;
}

/**
 * ThemeProvider Component
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children - Child components
 */
function ThemeProvider({ children }) {
  const appearance = useStore(settingsStore, (state) => state.appearance);
  const systemTheme = useSystemTheme();

  useEffect(() => {
    const root = document.documentElement;

    // Remove existing theme attribute
    root.removeAttribute('data-theme');

    // Determine effective theme
    let effectiveTheme = appearance;
    if (appearance === 'system') {
      effectiveTheme = systemTheme;
    }

    // Set the theme attribute
    if (effectiveTheme === 'transparent') {
      root.setAttribute('data-theme', 'transparent');
    } else if (effectiveTheme === 'light') {
      root.setAttribute('data-theme', 'light');
    } else if (effectiveTheme === 'dark') {
      root.setAttribute('data-theme', 'dark');
    } else {
      // Default to light
      root.setAttribute('data-theme', 'light');
    }

    console.log('[ThemeProvider] Theme set to:', effectiveTheme);
  }, [appearance, systemTheme]);

  return <>{children}</>;
}

export default ThemeProvider;

/**
 * Hook to access theme settings
 */
export function useTheme() {
  const appearance = useStore(settingsStore, (state) => state.appearance);
  const setAppearance = useStore(settingsStore, (state) => state.setAppearance);
  const toggleDarkMode = useStore(settingsStore, (state) => state.toggleDarkMode);

  return {
    appearance,
    setAppearance,
    toggleDarkMode,
    isDark: appearance === 'dark',
    isLight: appearance === 'light',
    isTransparent: appearance === 'transparent',
    isSystem: appearance === 'system',
  };
}
