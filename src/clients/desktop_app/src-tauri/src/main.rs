// Prevents additional console window on Windows in release mode
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python_daemon;

use python_daemon::PythonDaemon;
use tauri::Manager;
use std::path::PathBuf;

// Shared daemon state - holds the daemon process for lifecycle management
struct AppState {
    daemon: std::sync::Mutex<Option<PythonDaemon>>,
}

/// Read daemon port from file
/// Returns the port number if daemon is running, or default port if file doesn't exist
#[tauri::command]
fn get_daemon_port() -> serde_json::Value {
    let home = std::env::var("HOME").unwrap_or_else(|_| {
        std::env::var("USERPROFILE").unwrap_or_else(|_| String::from("~"))
    });
    let port_file = PathBuf::from(home).join(".ami").join("daemon.port");

    if !port_file.exists() {
        println!("Port file not found, using default port 8765");
        return serde_json::json!({
            "success": true,
            "port": 8765,
            "source": "default"
        });
    }

    match std::fs::read_to_string(&port_file) {
        Ok(content) => {
            match content.trim().parse::<u16>() {
                Ok(port) => {
                    println!("Read daemon port from file: {}", port);
                    serde_json::json!({
                        "success": true,
                        "port": port,
                        "source": "file"
                    })
                }
                Err(e) => {
                    println!("Failed to parse port file content '{}': {}", content, e);
                    serde_json::json!({
                        "success": true,
                        "port": 8765,
                        "source": "default",
                        "warning": format!("Invalid port file content: {}", e)
                    })
                }
            }
        }
        Err(e) => {
            println!("Failed to read port file: {}", e);
            serde_json::json!({
                "success": true,
                "port": 8765,
                "source": "default",
                "warning": format!("Failed to read port file: {}", e)
            })
        }
    }
}

/// Read daemon log file content (last N lines)
#[tauri::command]
fn read_daemon_logs(max_lines: Option<usize>) -> serde_json::Value {
    let max_lines = max_lines.unwrap_or(100);
    let home = std::env::var("HOME").unwrap_or_else(|_| String::from("~"));
    let log_path = PathBuf::from(home).join(".ami").join("logs").join("app.log");

    if !log_path.exists() {
        return serde_json::json!({
            "success": false,
            "error": "Log file not found",
            "path": log_path.to_string_lossy().to_string(),
            "logs": []
        });
    }

    match std::fs::read_to_string(&log_path) {
        Ok(content) => {
            let lines: Vec<&str> = content.lines().collect();
            let start = if lines.len() > max_lines { lines.len() - max_lines } else { 0 };
            let recent_lines: Vec<String> = lines[start..].iter().map(|s| s.to_string()).collect();

            serde_json::json!({
                "success": true,
                "path": log_path.to_string_lossy().to_string(),
                "logs": recent_lines,
                "total_lines": lines.len()
            })
        }
        Err(e) => {
            serde_json::json!({
                "success": false,
                "error": format!("Failed to read log file: {}", e),
                "path": log_path.to_string_lossy().to_string(),
                "logs": []
            })
        }
    }
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

/// DS-11: Open a file or folder with system default application
#[tauri::command]
fn open_path(path: String) -> serde_json::Value {
    let path_ref = std::path::Path::new(&path);

    if !path_ref.exists() {
        return serde_json::json!({
            "success": false,
            "error": format!("Path does not exist: {}", path)
        });
    }

    match open::that(&path) {
        Ok(_) => {
            println!("✓ Opened path: {}", path);
            serde_json::json!({
                "success": true,
                "path": path
            })
        }
        Err(e) => {
            println!("✗ Failed to open path {}: {}", path, e);
            serde_json::json!({
                "success": false,
                "error": format!("Failed to open: {}", e)
            })
        }
    }
}

/// DS-11: Reveal a file in system file explorer (Finder on macOS, Explorer on Windows)
#[tauri::command]
fn reveal_in_folder(path: String) -> serde_json::Value {
    let path_ref = std::path::Path::new(&path);

    if !path_ref.exists() {
        return serde_json::json!({
            "success": false,
            "error": format!("Path does not exist: {}", path)
        });
    }

    #[cfg(target_os = "macos")]
    {
        match std::process::Command::new("open")
            .args(["-R", &path])
            .spawn()
        {
            Ok(_) => {
                println!("✓ Revealed in Finder: {}", path);
                return serde_json::json!({
                    "success": true,
                    "path": path
                });
            }
            Err(e) => {
                println!("✗ Failed to reveal in Finder: {}", e);
                return serde_json::json!({
                    "success": false,
                    "error": format!("Failed to reveal: {}", e)
                });
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        match std::process::Command::new("explorer")
            .args(["/select,", &path])
            .spawn()
        {
            Ok(_) => {
                println!("✓ Revealed in Explorer: {}", path);
                return serde_json::json!({
                    "success": true,
                    "path": path
                });
            }
            Err(e) => {
                println!("✗ Failed to reveal in Explorer: {}", e);
                return serde_json::json!({
                    "success": false,
                    "error": format!("Failed to reveal: {}", e)
                });
            }
        }
    }

    #[cfg(target_os = "linux")]
    {
        // Linux doesn't have a standard "select file" command
        // Open the parent directory instead
        let parent = path_ref.parent()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| path.clone());

        match std::process::Command::new("xdg-open")
            .arg(&parent)
            .spawn()
        {
            Ok(_) => {
                println!("✓ Opened parent folder: {}", parent);
                return serde_json::json!({
                    "success": true,
                    "path": parent,
                    "note": "Opened parent folder (Linux limitation)"
                });
            }
            Err(e) => {
                println!("✗ Failed to open folder: {}", e);
                return serde_json::json!({
                    "success": false,
                    "error": format!("Failed to open folder: {}", e)
                });
            }
        }
    }

    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        serde_json::json!({
            "success": false,
            "error": "Unsupported platform"
        })
    }
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
        .invoke_handler(tauri::generate_handler![
            check_browser_installed,
            read_daemon_logs,
            get_daemon_port,
            open_path,
            reveal_in_folder
        ])
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
