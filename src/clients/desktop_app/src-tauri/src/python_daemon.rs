use std::process::{Child, Command, Stdio};

pub struct PythonDaemon {
    process: Option<Child>,
}

impl PythonDaemon {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        // Get project root (4 levels up from src-tauri: src-tauri -> desktop_app -> clients -> src -> root)
        let current_dir = std::env::current_dir()?;
        let project_root = current_dir
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .ok_or("Failed to find project root")?
            .to_path_buf();

        let daemon_path = project_root.join("src/app_backend/daemon.py");

        println!("Starting HTTP Python daemon from: {}", daemon_path.display());

        // Try multiple Python commands (python3, python, py)
        let python_commands = ["python3", "python", "py"];
        let mut process = None;
        let mut last_error = None;

        for cmd in &python_commands {
            match Command::new(cmd)
                .arg(&daemon_path)
                .current_dir(&project_root) // Run from project root
                .stdout(Stdio::inherit()) // Log stdout to console
                .stderr(Stdio::inherit()) // Log stderr to console
                .spawn()
            {
                Ok(p) => {
                    println!("Python HTTP daemon started with command: {} (PID: {})", cmd, p.id());
                    process = Some(p);
                    break;
                }
                Err(e) => {
                    println!("Failed to start with '{}': {}", cmd, e);
                    last_error = Some(e);
                }
            }
        }

        let process = process.ok_or_else(|| {
            format!(
                "Failed to start Python daemon. Tried commands: {:?}. Last error: {:?}",
                python_commands, last_error
            )
        })?;

        // Wait for HTTP daemon to initialize
        std::thread::sleep(std::time::Duration::from_secs(3));

        Ok(Self {
            process: Some(process),
        })
    }
}

impl Drop for PythonDaemon {
    fn drop(&mut self) {
        println!("Shutting down Python HTTP daemon...");
        if let Some(mut process) = self.process.take() {
            match process.kill() {
                Ok(_) => println!("Python daemon killed successfully"),
                Err(e) => println!("Error killing daemon: {}", e),
            }
            match process.wait() {
                Ok(status) => println!("Python daemon exited with status: {}", status),
                Err(e) => println!("Error waiting for daemon: {}", e),
            }
        }
    }
}
