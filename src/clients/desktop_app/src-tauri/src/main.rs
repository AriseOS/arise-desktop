// Prevents additional console window on Windows in release mode
// TEMPORARILY DISABLED for debugging - enable console to see error messages
// Uncomment the line below after debugging is complete
// #![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python_daemon;

use python_daemon::PythonDaemon;
use tauri::Manager;
use std::path::PathBuf;

// Shared daemon state - holds the daemon process for lifecycle management
struct AppState {
    daemon: std::sync::Mutex<Option<PythonDaemon>>,
}

/// Check if a usable browser is available (Chrome or Playwright Chromium)
#[tauri::command]
fn check_browser_installed() -> serde_json::Value {
    // Priority 1: Check for Google Chrome (user's installed browser)
    #[cfg(target_os = "macos")]
    let chrome_path = PathBuf::from("/Applications/Google Chrome.app");

    #[cfg(target_os = "windows")]
    let chrome_path = PathBuf::from("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe");

    #[cfg(target_os = "linux")]
    let chrome_path = PathBuf::from("/usr/bin/google-chrome");

    if chrome_path.exists() {
        println!("✓ Found Google Chrome at: {}", chrome_path.display());
        return serde_json::json!({
            "available": true,
            "browser_type": "chrome",
            "path": chrome_path.to_string_lossy().to_string(),
            "needs_install": false
        });
    }

    // Priority 2: Check for Playwright Chromium
    let home = std::env::var("HOME").unwrap_or_else(|_| String::from("~"));
    let playwright_cache = PathBuf::from(home)
        .join("Library")
        .join("Caches")
        .join("ms-playwright");

    if playwright_cache.exists() {
        if let Ok(entries) = std::fs::read_dir(&playwright_cache) {
            for entry in entries.flatten() {
                if let Some(name) = entry.file_name().to_str() {
                    if name.starts_with("chromium-") {
                        println!("✓ Found Playwright Chromium: {}", name);
                        return serde_json::json!({
                            "available": true,
                            "browser_type": "playwright-chromium",
                            "path": entry.path().to_string_lossy().to_string(),
                            "needs_install": false
                        });
                    }
                }
            }
        }
    }

    // No browser found
    println!("✗ No usable browser found. Will need to install Playwright Chromium.");
    serde_json::json!({
        "available": false,
        "browser_type": "none",
        "needs_install": true
    })
}

fn main() {
    println!("========================================");
    println!("Ami Desktop Application Starting");
    println!("========================================");
    println!("Current directory: {:?}", std::env::current_dir().unwrap_or_default());
    println!("Executable path: {:?}", std::env::current_exe().unwrap_or_default());
    println!("");

    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::default().build())
        .invoke_handler(tauri::generate_handler![check_browser_installed])
        .setup(|app| {
            // Initialize HTTP daemon on startup
            println!("🚀 Initializing Python HTTP daemon...");

            match PythonDaemon::new() {
                Ok(daemon) => {
                    println!("✅ Daemon started successfully. Frontend will connect to http://127.0.0.1:8765");

                    let app_state = AppState {
                        daemon: std::sync::Mutex::new(Some(daemon)),
                    };

                    app.manage(app_state);
                    Ok(())
                }
                Err(e) => {
                    eprintln!("❌ FATAL ERROR: Failed to initialize Python HTTP daemon");
                    eprintln!("Error details: {}", e);
                    eprintln!("");
                    eprintln!("Press Enter to exit...");

                    let mut input = String::new();
                    let _ = std::io::stdin().read_line(&mut input);

                    Err(Box::new(std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("Failed to initialize daemon: {}", e)
                    )))
                }
            }
        })
        .on_window_event(|_window, event| {
            // Handle window events
            match event {
                tauri::WindowEvent::CloseRequested { .. } => {
                    println!("🔴 Window close requested");
                }
                tauri::WindowEvent::Destroyed => {
                    println!("🔴 Window destroyed");
                }
                _ => {}
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            match event {
                tauri::RunEvent::Exit => {
                    println!("🔴 Application exiting...");

                    // Manually trigger daemon shutdown by taking it out of the Mutex
                    // This ensures Drop is called BEFORE Tauri exits
                    if let Some(state) = app_handle.try_state::<AppState>() {
                        if let Ok(mut daemon_guard) = state.daemon.lock() {
                            if let Some(daemon) = daemon_guard.take() {
                                println!("📍 Manually dropping daemon...");
                                drop(daemon); // Explicit drop triggers PythonDaemon::Drop
                                println!("📍 Daemon drop completed");
                            } else {
                                println!("⚠️  Daemon already dropped");
                            }
                        } else {
                            println!("❌ Failed to lock daemon mutex");
                        }
                    } else {
                        println!("❌ Failed to get AppState");
                    }
                }
                tauri::RunEvent::ExitRequested { .. } => {
                    println!("🔴 Exit requested");
                    // Exit will proceed, and RunEvent::Exit will handle cleanup
                }
                _ => {}
            }
        });
}
