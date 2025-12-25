use std::process::{Child, Command, Stdio};
use std::time::Duration;

pub struct PythonDaemon {
    process: Option<Child>,
    pid: Option<u32>,
}

impl PythonDaemon {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        // Start daemon process directly
        // If an old daemon is running on port 8765, the new one will fail to bind
        // and Python will exit with an error, which is the correct behavior
        let (process, pid) = Self::start_daemon_process()?;

        Ok(Self {
            process: Some(process),
            pid: Some(pid),
        })
    }

    /// Get Python script path for development mode
    fn get_python_script_path() -> Result<(String, Vec<String>), Box<dyn std::error::Error>> {
        let current_dir = std::env::current_dir()?;
        let project_root = current_dir
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .ok_or("Failed to find project root")?
            .to_path_buf();

        let daemon_path = project_root.join("src/app_backend/daemon.py");

        if !daemon_path.exists() {
            return Err(format!("Daemon not found at: {}", daemon_path.display()).into());
        }

        println!("Found daemon script: {}", daemon_path.display());
        Ok(("python3".to_string(), vec![daemon_path.to_string_lossy().to_string()]))
    }

    /// Detect if running in development or production mode and get daemon path
    fn get_daemon_path() -> Result<(String, Vec<String>), Box<dyn std::error::Error>> {
        println!("========================================");
        println!("Searching for daemon binary...");
        println!("========================================");

        // Check for dev mode override via environment variable
        if std::env::var("AMI_DEV_MODE").is_ok() {
            println!("🔧 AMI_DEV_MODE set, forcing Python script mode");
            return Self::get_python_script_path();
        }

        // Method 1: Check for bundled binary in resources directory (production mode)
        if let Ok(exe_path) = std::env::current_exe() {
            println!("Executable path: {}", exe_path.display());

            if let Some(exe_dir) = exe_path.parent() {
                println!("Executable directory: {}", exe_dir.display());

                // Platform-specific search paths
                #[cfg(target_os = "windows")]
                let possible_resources_dirs = {
                    // Windows: ami-desktop.exe and resources/ are in the same directory
                    // Structure: AmiPortable/
                    //            ├── ami-desktop.exe
                    //            └── resources/
                    //                └── ami-daemon/
                    //                    └── ami-daemon.exe
                    vec![
                        Some(exe_dir.join("resources")),
                    ]
                };

                #[cfg(target_os = "macos")]
                let possible_resources_dirs = {
                    // macOS: .app bundle structure
                    // Structure: Ami.app/
                    //            └── Contents/
                    //                ├── MacOS/
                    //                │   └── ami-desktop
                    //                └── Resources/
                    //                    └── ami-daemon.app/
                    //                        └── Contents/
                    //                            └── MacOS/
                    //                                └── ami-daemon
                    vec![
                        exe_dir.parent().map(|p| p.join("Resources").join("ami-daemon.app").join("Contents").join("MacOS")),
                        exe_dir.parent().map(|p| p.join("Resources").join("resources").join("ami-daemon.app").join("Contents").join("MacOS")),
                    ]
                };

                #[cfg(target_os = "linux")]
                let possible_resources_dirs = {
                    // Linux: similar to Windows portable structure
                    vec![
                        Some(exe_dir.join("resources")),
                    ]
                };

                #[cfg(target_os = "windows")]
                let binary_name = "ami-daemon.exe";
                #[cfg(not(target_os = "windows"))]
                let binary_name = "ami-daemon";

                println!("Platform-specific daemon search paths:");
                println!("");

                // Directory name doesn't include .exe extension (PyInstaller bundles are directories)
                let daemon_dir_name = if cfg!(target_os = "windows") {
                    "ami-daemon"
                } else {
                    binary_name
                };

                for (idx, resources_dir_opt) in possible_resources_dirs.iter().enumerate() {
                    if let Some(resources_dir) = resources_dir_opt {
                        println!("Search location #{}: {}", idx + 1, resources_dir.display());

                        // First, check if there's a daemon directory (e.g., resources/ami-daemon/)
                        let dir_path = resources_dir.join(daemon_dir_name);
                        println!("  - Checking for directory: {}", dir_path.display());

                        if dir_path.is_dir() {
                            println!("  - Directory exists, checking for nested binary...");
                            let nested_binary = dir_path.join(binary_name);
                            println!("  - Checking: {}", nested_binary.display());

                            if nested_binary.is_file() {
                                println!("  ✓ FOUND nested binary!");
                                println!("");
                                return Ok((nested_binary.to_string_lossy().to_string(), vec![]));
                            } else {
                                println!("  ✗ Nested binary not found");
                            }
                        } else {
                            // Not a directory, check if it's a file directly (e.g., resources/ami-daemon.exe)
                            println!("  - Not a directory, checking as file...");
                            println!("  - Checking: {}", dir_path.display());

                            if dir_path.is_file() {
                                println!("  ✓ FOUND as file!");
                                println!("");
                                return Ok((dir_path.to_string_lossy().to_string(), vec![]));
                            } else {
                                println!("  ✗ Not found");
                            }
                        }
                        println!("");
                    }
                }

                println!("❌ Daemon binary not found in any expected location");
                println!("");
            }
        }

        // Method 2: Development mode - use Python script
        println!("Trying development mode (Python script)...");
        Self::get_python_script_path()
    }

    /// Start the daemon process with proper process group configuration
    fn start_daemon_process() -> Result<(Child, u32), Box<dyn std::error::Error>> {
        // Get daemon path (binary or script)
        let (command, args) = Self::get_daemon_path()?;

        println!("Starting daemon with command: {} {:?}", command, args);

        // If using Python script, try multiple Python commands
        let commands_to_try = if command == "python3" {
            vec!["python3", "python", "py"]
        } else {
            vec![command.as_str()]
        };

        let mut last_error = None;

        for cmd in &commands_to_try {
            #[cfg(unix)]
            {
                let mut command = Command::new(cmd);

                // Add arguments if any (for Python script mode)
                if !args.is_empty() {
                    command.args(&args);
                }

                // Do NOT use setsid() - keep daemon.py as child process of Tauri
                // This allows OS to automatically manage process lifecycle:
                // - When Tauri exits, daemon.py receives SIGHUP automatically
                // - Child::drop() will wait for daemon.py to exit
                // - Simpler and more reliable process management
                match command
                    .stdout(Stdio::inherit())
                    .stderr(Stdio::inherit())
                    .spawn()
                {
                    Ok(p) => {
                        let pid = p.id();
                        println!("Daemon started with '{}' (PID: {})", cmd, pid);
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
                let mut command = Command::new(cmd);

                // Add arguments if any (for Python script mode)
                if !args.is_empty() {
                    command.args(&args);
                }

                // On Windows, use Stdio::null() to prevent console window from appearing
                // The daemon logs to file anyway, so we don't need console output
                match command
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .spawn()
                {
                    Ok(p) => {
                        let pid = p.id();
                        println!("Daemon started with '{}' (PID: {})", cmd, pid);
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
            "Failed to start daemon. Tried commands: {:?}. Last error: {:?}",
            commands_to_try, last_error
        )
        .into())
    }
}

impl Drop for PythonDaemon {
    fn drop(&mut self) {
        println!("=== PythonDaemon Drop called ===");
        println!("Shutting down Python HTTP daemon...");

        // Send SIGTERM to daemon process for graceful shutdown
        // Since we removed setsid() (方案1), daemon.py is a direct child process
        if let Some(mut process) = self.process.take() {
            let pid = process.id();
            println!("Sending SIGTERM to daemon process (PID: {})...", pid);

            // Send SIGTERM (graceful shutdown signal)
            #[cfg(unix)]
            {
                use nix::sys::signal::{self, Signal};
                use nix::unistd::Pid;

                match signal::kill(Pid::from_raw(pid as i32), Signal::SIGTERM) {
                    Ok(_) => {
                        println!("SIGTERM sent, waiting for process to exit...");

                        // Wait for process to exit (with timeout)
                        match Self::wait_with_timeout(&mut process, Duration::from_secs(5)) {
                            Ok(status) => {
                                println!("✅ Daemon exited gracefully with status: {}", status);
                            }
                            Err(e) => {
                                println!("⚠️  Daemon did not exit within timeout: {}", e);
                                println!("   Sending SIGKILL to force termination...");
                                let _ = process.kill(); // Force kill as last resort
                            }
                        }
                    }
                    Err(e) => {
                        println!("❌ Failed to send SIGTERM: {}", e);
                        println!("   Trying SIGKILL...");
                        let _ = process.kill();
                    }
                }
            }

            #[cfg(not(unix))]
            {
                // Windows: use kill() which terminates the process
                match process.kill() {
                    Ok(_) => {
                        println!("Termination signal sent, waiting for process to exit...");
                        match process.wait() {
                            Ok(status) => println!("✅ Daemon exited with status: {}", status),
                            Err(e) => println!("⚠️  Error waiting for daemon: {}", e),
                        }
                    }
                    Err(e) => {
                        println!("❌ Failed to terminate daemon: {}", e);
                    }
                }
            }
        } else {
            println!("⚠️  No process handle available");
        }

        println!("=== PythonDaemon Drop completed ===");
    }
}

impl PythonDaemon {
    /// Wait for process to exit with timeout
    fn wait_with_timeout(
        process: &mut Child,
        timeout: Duration,
    ) -> Result<std::process::ExitStatus, String> {
        use std::thread;

        // Use try_wait() in a loop to check if process has exited
        let start = std::time::Instant::now();

        loop {
            // Check if process has exited
            match process.try_wait() {
                Ok(Some(status)) => {
                    return Ok(status);
                }
                Ok(None) => {
                    // Process still running
                    if start.elapsed() >= timeout {
                        return Err("Process did not exit within timeout".to_string());
                    }
                    // Sleep a bit before checking again
                    thread::sleep(Duration::from_millis(100));
                }
                Err(e) => {
                    return Err(format!("Error checking process status: {}", e));
                }
            }
        }
    }
}
