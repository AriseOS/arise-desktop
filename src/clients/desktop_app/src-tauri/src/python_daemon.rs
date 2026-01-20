use std::process::{Child, Command, Stdio};
use std::time::Duration;
#[cfg(windows)]
use std::path::PathBuf;

pub struct PythonDaemon {
    process: Option<Child>,
    #[cfg(windows)]
    daemon_port: Option<u16>,
}

impl PythonDaemon {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        // Start daemon process directly
        // If an old daemon is running on port 8765, the new one will fail to bind
        // and Python will exit with an error, which is the correct behavior
        let (process, _pid) = Self::start_daemon_process()?;

        #[cfg(windows)]
        {
            // On Windows, wait for port file and store port for HTTP shutdown
            let daemon_port = Self::wait_for_daemon_port(Duration::from_secs(30))?;
            println!("Daemon port discovered: {}", daemon_port);

            Ok(Self {
                process: Some(process),
                daemon_port: Some(daemon_port),
            })
        }

        #[cfg(not(windows))]
        {
            Ok(Self {
                process: Some(process),
            })
        }
    }

    /// Get the path to the daemon port file (Windows only)
    #[cfg(windows)]
    fn get_port_file_path() -> PathBuf {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .unwrap_or_else(|_| String::from("~"));
        PathBuf::from(home).join(".ami").join("daemon.port")
    }

    /// Wait for daemon to write its port file (Windows only)
    #[cfg(windows)]
    fn wait_for_daemon_port(timeout: Duration) -> Result<u16, Box<dyn std::error::Error>> {
        use std::thread;

        let port_file = Self::get_port_file_path();
        let start = std::time::Instant::now();

        println!("Waiting for daemon port file: {}", port_file.display());

        loop {
            if port_file.exists() {
                match std::fs::read_to_string(&port_file) {
                    Ok(content) => {
                        if let Ok(port) = content.trim().parse::<u16>() {
                            return Ok(port);
                        }
                    }
                    Err(_) => {
                        // File might still be written, continue waiting
                    }
                }
            }

            if start.elapsed() >= timeout {
                // Return default port if timeout
                println!("⚠️  Timeout waiting for port file, using default port 8765");
                return Ok(8765);
            }

            thread::sleep(Duration::from_millis(100));
        }
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

        let daemon_path = project_root.join("src/clients/desktop_app/ami_daemon/daemon.py");

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

            // Unix: Use SIGTERM for graceful shutdown
            #[cfg(unix)]
            {
                use nix::sys::signal::{self, Signal};
                use nix::unistd::Pid;

                println!("Sending SIGTERM to daemon process (PID: {})...", pid);

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

            // Windows: Use HTTP shutdown for graceful cleanup, then force kill
            #[cfg(windows)]
            {
                println!("Windows: Using HTTP shutdown for graceful termination (PID: {})...", pid);

                let mut http_shutdown_success = false;

                // Try HTTP shutdown first
                if let Some(port) = self.daemon_port {
                    let shutdown_url = format!("http://127.0.0.1:{}/api/v1/app/shutdown", port);
                    println!("Sending HTTP shutdown request to: {}", shutdown_url);

                    // Use reqwest blocking client with short timeout
                    match reqwest::blocking::Client::builder()
                        .timeout(Duration::from_secs(2))
                        .build()
                    {
                        Ok(client) => {
                            match client.post(&shutdown_url).send() {
                                Ok(response) => {
                                    if response.status().is_success() {
                                        println!("✅ HTTP shutdown request accepted");
                                        http_shutdown_success = true;
                                    } else {
                                        println!("⚠️  HTTP shutdown returned status: {}", response.status());
                                    }
                                }
                                Err(e) => {
                                    println!("⚠️  HTTP shutdown request failed: {}", e);
                                }
                            }
                        }
                        Err(e) => {
                            println!("⚠️  Failed to create HTTP client: {}", e);
                        }
                    }
                } else {
                    println!("⚠️  No daemon port available for HTTP shutdown");
                }

                // Wait for process to exit (longer timeout if HTTP shutdown was sent)
                let wait_timeout = if http_shutdown_success {
                    Duration::from_secs(10) // Give more time for graceful cleanup
                } else {
                    Duration::from_secs(1)
                };

                match Self::wait_with_timeout(&mut process, wait_timeout) {
                    Ok(status) => {
                        println!("✅ Daemon exited with status: {}", status);
                    }
                    Err(e) => {
                        println!("⚠️  Daemon did not exit within timeout: {}", e);
                        println!("   Force killing process...");
                        match process.kill() {
                            Ok(_) => {
                                match process.wait() {
                                    Ok(status) => println!("✅ Daemon force killed with status: {}", status),
                                    Err(e) => println!("⚠️  Error waiting for daemon: {}", e),
                                }
                            }
                            Err(e) => {
                                println!("❌ Failed to kill daemon: {}", e);
                            }
                        }
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
