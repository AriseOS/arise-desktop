// Prevents additional console window on Windows in release mode
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python_daemon;

use python_daemon::PythonDaemon;
use tauri::Manager;

// Shared daemon state - holds the daemon process for lifecycle management
struct AppState {
    daemon: std::sync::Mutex<Option<PythonDaemon>>,
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_store::Builder::default().build())
        .setup(|app| {
            // Initialize HTTP daemon on startup
            println!("🚀 Initializing Python HTTP daemon...");
            let daemon = PythonDaemon::new()
                .expect("Failed to initialize Python HTTP daemon");

            println!("✅ Daemon started successfully. Frontend will connect to http://127.0.0.1:8765");

            let app_state = AppState {
                daemon: std::sync::Mutex::new(Some(daemon)),
            };

            app.manage(app_state);
            Ok(())
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
