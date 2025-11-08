use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

pub struct PythonDaemon {
    stdin: Arc<Mutex<ChildStdin>>,
    stdout: Arc<Mutex<ChildStdout>>,
    process: Child,
    request_id: Arc<AtomicU64>,
}

impl PythonDaemon {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        // Get project root (3 levels up from src-tauri)
        let current_dir = std::env::current_dir()?;
        let project_root = current_dir
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .ok_or("Failed to find project root")?
            .to_path_buf();

        let daemon_path = project_root.join("src/app_backend/daemon.py");

        println!("Starting Python daemon from: {}", daemon_path.display());

        // Start Python daemon process
        let mut process = Command::new("python")
            .arg(&daemon_path)
            .current_dir(project_root) // Run from project root
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit()) // Log stderr to console
            .spawn()?;

        println!("Python daemon started with PID: {}", process.id());

        // Take stdin and stdout
        let stdin = process.stdin.take().expect("Failed to get stdin");
        let stdout = process.stdout.take().expect("Failed to get stdout");

        // Wait for daemon to initialize
        std::thread::sleep(std::time::Duration::from_secs(8));

        Ok(Self {
            stdin: Arc::new(Mutex::new(stdin)),
            stdout: Arc::new(Mutex::new(stdout)),
            process,
            request_id: Arc::new(AtomicU64::new(1)),
        })
    }

    pub async fn call_method(
        &self,
        method: &str,
        params: Value,
    ) -> Result<Value, Box<dyn std::error::Error>> {
        // Get unique request ID
        let id = self.request_id.fetch_add(1, Ordering::SeqCst);

        // Build JSON-RPC request
        let request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        // Send request
        {
            let mut stdin = self.stdin.lock().unwrap();
            let request_str = serde_json::to_string(&request)?;
            writeln!(stdin, "{}", request_str)?;
            stdin.flush()?;
            println!("→ Sent: {}", request_str);
        }

        // Read response - skip non-JSON lines (print statements)
        {
            let mut stdout = self.stdout.lock().unwrap();
            let mut reader = BufReader::new(&mut *stdout);

            // Keep reading lines until we get valid JSON
            loop {
                let mut response_str = String::new();
                reader.read_line(&mut response_str)?;

                let trimmed = response_str.trim();
                if trimmed.is_empty() {
                    continue;
                }

                println!("← Received: {}", trimmed);

                // Try to parse as JSON
                match serde_json::from_str::<Value>(trimmed) {
                    Ok(response) => {
                        // Valid JSON-RPC response
                        if response.get("jsonrpc").is_some() {
                            if let Some(error) = response.get("error") {
                                return Err(format!("Daemon error: {}", error).into());
                            }

                            if let Some(result) = response.get("result") {
                                return Ok(result.clone());
                            } else {
                                return Err("Invalid response format".into());
                            }
                        } else {
                            // Not a JSON-RPC response, skip
                            println!("  (skipping non-RPC JSON)");
                            continue;
                        }
                    }
                    Err(_) => {
                        // Not JSON, probably a print statement - skip
                        println!("  (skipping non-JSON line)");
                        continue;
                    }
                }
            }
        }
    }
}

impl Drop for PythonDaemon {
    fn drop(&mut self) {
        println!("Shutting down Python daemon...");
        let _ = self.process.kill();
        let _ = self.process.wait();
    }
}
