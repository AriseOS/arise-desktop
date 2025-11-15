use std::process::{Child, Command, Stdio};
use std::time::Duration;

pub struct PythonDaemon {
    process: Option<Child>,
    pid: Option<u32>,
}

impl PythonDaemon {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        // Step 1: Try to shutdown old daemon gracefully via HTTP
        Self::cleanup_old_daemon_http();

        // Step 2: Start new daemon process
        let (process, pid) = Self::start_daemon_process()?;

        Ok(Self {
            process: Some(process),
            pid: Some(pid),
        })
    }

    /// Try to shutdown old daemon via HTTP endpoint (graceful shutdown)
    fn cleanup_old_daemon_http() {
        println!("Checking for old daemon process...");

        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build();

        match client {
            Ok(client) => {
                match client
                    .post("http://127.0.0.1:8765/api/shutdown")
                    .send()
                {
                    Ok(response) => {
                        if response.status().is_success() {
                            println!("Sent shutdown request to old daemon, waiting for graceful shutdown...");
                            std::thread::sleep(Duration::from_secs(3));
                            println!("Old daemon should have shut down gracefully");
                        } else {
                            println!("Old daemon responded with non-success status: {}", response.status());
                        }
                    }
                    Err(_) => {
                        println!("No old daemon running (connection refused)");
                    }
                }
            }
            Err(e) => {
                println!("Failed to create HTTP client: {}", e);
            }
        }
    }

    /// Start the daemon process with proper process group configuration
    fn start_daemon_process() -> Result<(Child, u32), Box<dyn std::error::Error>> {
        // Get project root (4 levels up from src-tauri)
        let current_dir = std::env::current_dir()?;
        let project_root = current_dir
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .ok_or("Failed to find project root")?
            .to_path_buf();

        let daemon_path = project_root.join("src/app_backend/daemon.py");

        println!("Starting Python HTTP daemon from: {}", daemon_path.display());

        // Try multiple Python commands
        let python_commands = ["python3", "python", "py"];
        let mut last_error = None;

        for cmd in &python_commands {
            #[cfg(unix)]
            {
                use std::os::unix::process::CommandExt;

                match unsafe {
                    Command::new(cmd)
                        .arg(&daemon_path)
                        .current_dir(&project_root)
                        .stdout(Stdio::inherit())
                        .stderr(Stdio::inherit())
                        .pre_exec(|| {
                            // Create new session (process group) with this process as leader
                            // This ensures all child processes can be killed together
                            nix::unistd::setsid().map_err(|e| {
                                std::io::Error::new(std::io::ErrorKind::Other, e.to_string())
                            })?;
                            Ok(())
                        })
                        .spawn()
                } {
                    Ok(p) => {
                        let pid = p.id();
                        println!(
                            "Python daemon started with '{}' (PID: {}, Process Group: {})",
                            cmd, pid, pid
                        );
                        return Ok((p, pid));
                    }
                    Err(e) => {
                        println!("Failed to start with '{}': {}", cmd, e);
                        last_error = Some(e);
                    }
                }
            }

            #[cfg(not(unix))]
            {
                match Command::new(cmd)
                    .arg(&daemon_path)
                    .current_dir(&project_root)
                    .stdout(Stdio::inherit())
                    .stderr(Stdio::inherit())
                    .spawn()
                {
                    Ok(p) => {
                        let pid = p.id();
                        println!("Python daemon started with '{}' (PID: {})", cmd, pid);
                        return Ok((p, pid));
                    }
                    Err(e) => {
                        println!("Failed to start with '{}': {}", cmd, e);
                        last_error = Some(e);
                    }
                }
            }
        }

        Err(format!(
            "Failed to start Python daemon. Tried commands: {:?}. Last error: {:?}",
            python_commands, last_error
        )
        .into())
    }
}

impl Drop for PythonDaemon {
    fn drop(&mut self) {
        println!("Shutting down Python HTTP daemon...");

        // Phase 1: Try graceful HTTP shutdown first
        self.try_graceful_http_shutdown();

        // Phase 2: Use signals for cleanup
        if let Some(pid) = self.pid {
            #[cfg(unix)]
            {
                self.unix_two_phase_termination(pid);
            }

            #[cfg(not(unix))]
            {
                self.windows_termination();
            }
        }
    }
}

impl PythonDaemon {
    /// Try to gracefully shutdown via HTTP endpoint
    fn try_graceful_http_shutdown(&self) {
        println!("Attempting graceful shutdown via HTTP...");

        let client = reqwest::blocking::Client::builder()
            .timeout(Duration::from_secs(2))
            .build();

        match client {
            Ok(client) => {
                match client
                    .post("http://127.0.0.1:8765/api/shutdown")
                    .send()
                {
                    Ok(_) => {
                        println!("Shutdown request sent, waiting for daemon to exit...");
                        std::thread::sleep(Duration::from_secs(2));
                    }
                    Err(e) => {
                        println!("HTTP shutdown failed: {} (will use signal-based shutdown)", e);
                    }
                }
            }
            Err(e) => {
                println!("Failed to create HTTP client: {} (will use signal-based shutdown)", e);
            }
        }
    }

    /// Unix: Two-phase termination (SIGTERM → wait → SIGKILL)
    #[cfg(unix)]
    fn unix_two_phase_termination(&self, pid: u32) {
        use nix::sys::signal::{self, Signal};
        use nix::unistd::Pid;

        let pid = Pid::from_raw(pid as i32);

        println!("Phase 1: Sending SIGTERM to process group {}", pid);

        // Send SIGTERM to entire process group (negative PID)
        match signal::killpg(Pid::from_raw(pid.as_raw()), Signal::SIGTERM) {
            Ok(_) => {
                println!("SIGTERM sent, waiting up to 3 seconds for graceful shutdown...");

                // Wait for up to 3 seconds for process to exit
                for i in 0..30 {
                    std::thread::sleep(Duration::from_millis(100));

                    // Check if process still exists (signal 0 = existence check)
                    match signal::kill(pid, None) {
                        Err(_) => {
                            println!("✅ Process exited gracefully");
                            return;
                        }
                        Ok(_) => {
                            // Process still running
                            if i == 29 {
                                println!("⚠️  Process didn't exit after SIGTERM timeout");
                            }
                        }
                    }
                }

                // Phase 2: Force kill with SIGKILL
                println!("Phase 2: Sending SIGKILL to force termination...");
                match signal::killpg(Pid::from_raw(pid.as_raw()), Signal::SIGKILL) {
                    Ok(_) => println!("SIGKILL sent to process group"),
                    Err(e) => println!("Failed to send SIGKILL: {}", e),
                }

                // Final wait
                std::thread::sleep(Duration::from_millis(500));
                match signal::kill(pid, None) {
                    Err(_) => println!("✅ Process forcefully terminated"),
                    Ok(_) => println!("⚠️  Process may still be running (zombie or stuck)"),
                }
            }
            Err(e) => {
                println!(
                    "Failed to send SIGTERM: {}, trying SIGKILL directly",
                    e
                );
                let _ = signal::killpg(Pid::from_raw(pid.as_raw()), Signal::SIGKILL);
            }
        }
    }

    /// Windows: Direct termination
    #[cfg(not(unix))]
    fn windows_termination(&mut self) {
        if let Some(mut process) = self.process.take() {
            match process.kill() {
                Ok(_) => {
                    println!("Process kill signal sent");
                    match process.wait() {
                        Ok(status) => println!("Process exited with status: {}", status),
                        Err(e) => println!("Error waiting for process: {}", e),
                    }
                }
                Err(e) => println!("Error killing process: {}", e),
            }
        }
    }
}
