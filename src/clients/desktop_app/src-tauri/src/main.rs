// Prevents additional console window on Windows in release mode
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python_daemon;

use python_daemon::PythonDaemon;
use tauri::Manager;

// Shared daemon state - just holds the daemon process for lifecycle management
struct AppState {
    _daemon: PythonDaemon,
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::default().build())
        .setup(|app| {
            // Initialize HTTP daemon on startup
            println!("Initializing Python HTTP daemon...");
            let daemon = PythonDaemon::new()
                .expect("Failed to initialize Python HTTP daemon");

            println!("Daemon started successfully. Frontend will connect to http://127.0.0.1:8765");

            let app_state = AppState {
                _daemon: daemon,
            };

            app.manage(app_state);
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
