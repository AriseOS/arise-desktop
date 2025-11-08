// Prevents additional console window on Windows in release mode
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod python_daemon;

use python_daemon::PythonDaemon;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tauri::Manager;
use tokio::sync::Mutex;

// Shared daemon state
struct AppState {
    daemon: Arc<Mutex<Option<PythonDaemon>>>,
}

// Request/Response types
#[derive(Debug, Serialize, Deserialize)]
struct StartRecordingRequest {
    url: String,
    title: String,
    description: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct StopRecordingResponse {
    session_id: String,
    operations_count: i32,
    local_file_path: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct GenerateWorkflowRequest {
    session_id: String,
    title: String,
    description: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct GenerateWorkflowResponse {
    workflow_name: String,
    local_path: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ExecuteWorkflowRequest {
    workflow_name: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ExecuteWorkflowResponse {
    task_id: String,
    status: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct WorkflowStatusResponse {
    task_id: String,
    status: String,
    progress: i32,
    current_step: i32,
    total_steps: i32,
    message: String,
    result: Option<serde_json::Value>,
    error: Option<String>,
}

// Tauri Commands

#[tauri::command]
async fn start_recording(
    state: tauri::State<'_, AppState>,
    url: String,
    title: String,
    description: String,
) -> Result<serde_json::Value, String> {
    println!("🎬 Rust: start_recording called with url={}, title={}, description={}", url, title, description);

    let daemon = state.daemon.lock().await;
    if let Some(daemon) = daemon.as_ref() {
        let params = serde_json::json!({
            "url": url,
            "title": title,
            "description": description,
        });

        println!("🎬 Rust: Calling daemon.call_method...");
        let result = daemon.call_method("start_recording", params)
            .await
            .map_err(|e| {
                println!("❌ Rust: start_recording failed: {}", e);
                format!("Failed to start recording: {}", e)
            });

        println!("🎬 Rust: start_recording result: {:?}", result);
        result
    } else {
        println!("❌ Rust: Daemon not initialized");
        Err("Daemon not initialized".to_string())
    }
}

#[tauri::command]
async fn stop_recording(
    state: tauri::State<'_, AppState>,
) -> Result<StopRecordingResponse, String> {
    let daemon = state.daemon.lock().await;
    if let Some(daemon) = daemon.as_ref() {
        let result = daemon.call_method("stop_recording", serde_json::json!({}))
            .await
            .map_err(|e| format!("Failed to stop recording: {}", e))?;

        serde_json::from_value(result)
            .map_err(|e| format!("Failed to parse response: {}", e))
    } else {
        Err("Daemon not initialized".to_string())
    }
}

#[tauri::command]
async fn generate_workflow(
    state: tauri::State<'_, AppState>,
    session_id: String,
    title: String,
    description: String,
) -> Result<GenerateWorkflowResponse, String> {
    let daemon = state.daemon.lock().await;
    if let Some(daemon) = daemon.as_ref() {
        let params = serde_json::json!({
            "session_id": session_id,
            "title": title,
            "description": description,
            "user_id": "default_user",
        });

        let result = daemon.call_method("generate_workflow_from_recording", params)
            .await
            .map_err(|e| format!("Failed to generate workflow: {}", e))?;

        serde_json::from_value(result)
            .map_err(|e| format!("Failed to parse response: {}", e))
    } else {
        Err("Daemon not initialized".to_string())
    }
}

#[tauri::command]
async fn execute_workflow(
    state: tauri::State<'_, AppState>,
    workflow_name: String,
) -> Result<ExecuteWorkflowResponse, String> {
    let daemon = state.daemon.lock().await;
    if let Some(daemon) = daemon.as_ref() {
        let params = serde_json::json!({
            "workflow_name": workflow_name,
            "user_id": "default_user",
        });

        let result = daemon.call_method("execute_workflow", params)
            .await
            .map_err(|e| format!("Failed to execute workflow: {}", e))?;

        serde_json::from_value(result)
            .map_err(|e| format!("Failed to parse response: {}", e))
    } else {
        Err("Daemon not initialized".to_string())
    }
}

#[tauri::command]
async fn get_workflow_status(
    state: tauri::State<'_, AppState>,
    task_id: String,
) -> Result<WorkflowStatusResponse, String> {
    let daemon = state.daemon.lock().await;
    if let Some(daemon) = daemon.as_ref() {
        let params = serde_json::json!({
            "task_id": task_id,
        });

        let result = daemon.call_method("get_workflow_status", params)
            .await
            .map_err(|e| format!("Failed to get status: {}", e))?;

        serde_json::from_value(result)
            .map_err(|e| format!("Failed to parse response: {}", e))
    } else {
        Err("Daemon not initialized".to_string())
    }
}

#[tauri::command]
async fn list_workflows(
    state: tauri::State<'_, AppState>,
) -> Result<Vec<String>, String> {
    let daemon = state.daemon.lock().await;
    if let Some(daemon) = daemon.as_ref() {
        let params = serde_json::json!({
            "user_id": "default_user",
        });

        let result = daemon.call_method("list_workflows", params)
            .await
            .map_err(|e| format!("Failed to list workflows: {}", e))?;

        let workflows: serde_json::Value = serde_json::from_value(result)
            .map_err(|e| format!("Failed to parse response: {}", e))?;

        serde_json::from_value(workflows["workflows"].clone())
            .map_err(|e| format!("Failed to parse workflows list: {}", e))
    } else {
        Err("Daemon not initialized".to_string())
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Initialize daemon on startup
            let daemon = PythonDaemon::new()
                .expect("Failed to initialize Python daemon");

            let app_state = AppState {
                daemon: Arc::new(Mutex::new(Some(daemon))),
            };

            app.manage(app_state);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            start_recording,
            stop_recording,
            generate_workflow,
            execute_workflow,
            get_workflow_status,
            list_workflows,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
