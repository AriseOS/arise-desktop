/**
 * DaemonLauncher — TypeScript daemon lifecycle management.
 *
 * Dev mode (AMI_DEV_MODE=1): runs daemon-ts via tsx or compiled dist/server.js
 * Production: runs bundled daemon-ts/dist/server.js from app resources
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');
const kill = require('tree-kill');

const PORT_FILE = path.join(os.homedir(), '.ami', 'daemon.port');

class DaemonLauncher {
  constructor(cdpPort) {
    this.cdpPort = cdpPort;
    this.process = null;
    this.daemonPort = null;
  }

  /**
   * Start the daemon process and wait for it to write its port file.
   */
  async start() {
    const { command, args } = this._getDaemonPath();
    console.log(`[DaemonLauncher] Starting daemon: ${command} ${args.join(' ')}`);

    // Delete stale port file from previous run to avoid false-positive detection
    try {
      if (fs.existsSync(PORT_FILE)) {
        fs.unlinkSync(PORT_FILE);
        console.log('[DaemonLauncher] Removed stale port file');
      }
    } catch (e) {
      console.warn(`[DaemonLauncher] Failed to remove stale port file: ${e.message}`);
    }

    const env = { ...process.env, BROWSER_CDP_PORT: String(this.cdpPort) };

    // On Unix, inherit stdio so logs appear in terminal during dev.
    // On Windows, hide the console window by using 'ignore'.
    const stdio = process.platform === 'win32' ? 'ignore' : 'inherit';

    this.process = spawn(command, args, { env, stdio });

    this.process.on('error', (err) => {
      console.error(`[DaemonLauncher] Failed to start daemon: ${err.message}`);
    });

    this.process.on('exit', (code, signal) => {
      console.log(`[DaemonLauncher] Daemon exited (code=${code}, signal=${signal})`);
      this.process = null;
    });

    // Wait for daemon to write its port file (up to 30s)
    this.daemonPort = await this._waitForPortFile(30000);
    console.log(`[DaemonLauncher] Daemon port discovered: ${this.daemonPort}`);
  }

  /**
   * Gracefully stop the daemon process.
   */
  async stop() {
    if (!this.process) return;

    const pid = this.process.pid;
    console.log(`[DaemonLauncher] Stopping daemon (PID: ${pid})...`);

    if (process.platform === 'win32') {
      // Windows: HTTP shutdown first, then force kill
      await this._shutdownWindows(pid);
    } else {
      // Unix: SIGTERM, wait, then SIGKILL
      await this._shutdownUnix(pid);
    }

    this.process = null;
  }

  getDaemonPort() {
    return this.daemonPort;
  }

  // ---- Private helpers ----

  _getDaemonPath() {
    // Dev mode: use source files directly
    if (process.env.AMI_DEV_MODE) {
      console.log('[DaemonLauncher] AMI_DEV_MODE set, using TypeScript daemon (tsx)');
      return this._getTSDaemonDevPath();
    }

    // Production mode: bundled TS daemon
    const resourcesPath = process.resourcesPath;
    const tsBundlePath = path.join(resourcesPath, 'daemon-ts', 'dist', 'server.js');
    if (fs.existsSync(tsBundlePath)) {
      console.log(`[DaemonLauncher] Found bundled TS daemon: ${tsBundlePath}`);
      return { command: process.execPath, args: [tsBundlePath] };
    }

    // Fallback to dev mode
    console.log('[DaemonLauncher] No bundled daemon found, falling back to TS dev mode');
    return this._getTSDaemonDevPath();
  }

  _getTSDaemonDevPath() {
    // Walk up from electron/ to find the project root
    const projectRoot = path.resolve(__dirname, '..', '..', '..', '..');
    const desktopApp = path.join(projectRoot, 'src', 'clients', 'desktop_app');

    // Dev mode: prefer tsx (source) so code changes take effect without rebuild
    const srcEntry = path.join(desktopApp, 'daemon-ts', 'src', 'server.ts');
    if (fs.existsSync(srcEntry)) {
      console.log(`[DaemonLauncher] Using tsx for TS daemon: ${srcEntry}`);
      return { command: 'npx', args: ['tsx', srcEntry] };
    }

    // Fall back to compiled JS
    const distEntry = path.join(desktopApp, 'daemon-ts', 'dist', 'server.js');
    if (fs.existsSync(distEntry)) {
      console.log(`[DaemonLauncher] Using compiled TS daemon: ${distEntry}`);
      return { command: 'node', args: [distEntry] };
    }

    throw new Error(`TypeScript daemon not found. Checked:\n  ${srcEntry}\n  ${distEntry}`);
  }

  _waitForPortFile(timeoutMs) {
    return new Promise((resolve, reject) => {
      const startTime = Date.now();
      const interval = setInterval(() => {
        try {
          if (fs.existsSync(PORT_FILE)) {
            const content = fs.readFileSync(PORT_FILE, 'utf-8').trim();
            const port = parseInt(content, 10);
            if (!isNaN(port) && port > 0) {
              clearInterval(interval);
              resolve(port);
              return;
            }
          }
        } catch {
          // File may still be written, continue
        }

        if (Date.now() - startTime >= timeoutMs) {
          clearInterval(interval);
          console.warn('[DaemonLauncher] Timeout waiting for port file, using default 8765');
          resolve(8765);
        }
      }, 100);
    });
  }

  async _shutdownUnix(pid) {
    try {
      // Use tree-kill to kill the entire process tree (daemon + subprocesses)
      await new Promise((resolve) => {
        kill(pid, 'SIGTERM', (err) => {
          if (err) {
            console.warn(`[DaemonLauncher] tree-kill SIGTERM error: ${err.message}`);
          }
          resolve();
        });
      });
      console.log('[DaemonLauncher] SIGTERM sent to process tree, waiting...');

      const exited = await this._waitForExit(5000);
      if (exited) {
        console.log('[DaemonLauncher] Daemon exited gracefully');
      } else {
        console.warn('[DaemonLauncher] Daemon did not exit in time, sending SIGKILL');
        kill(pid, 'SIGKILL', () => {});
      }
    } catch {
      // Process already exited
    }
  }

  async _shutdownWindows(pid) {
    let httpSuccess = false;

    // Try HTTP shutdown
    if (this.daemonPort) {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 2000);
        await fetch(`http://127.0.0.1:${this.daemonPort}/api/v1/app/shutdown`, {
          method: 'POST',
          signal: controller.signal,
        });
        clearTimeout(timeout);
        httpSuccess = true;
        console.log('[DaemonLauncher] HTTP shutdown request accepted');
      } catch {
        console.warn('[DaemonLauncher] HTTP shutdown request failed');
      }
    }

    const waitTime = httpSuccess ? 10000 : 1000;
    const exited = await this._waitForExit(waitTime);
    if (!exited) {
      console.warn('[DaemonLauncher] Force killing daemon process tree');
      kill(pid, 'SIGKILL', () => {});
    }
  }

  _waitForExit(timeoutMs) {
    return new Promise((resolve) => {
      if (!this.process) {
        resolve(true);
        return;
      }

      const onExit = () => {
        clearTimeout(timer);
        resolve(true);
      };

      const timer = setTimeout(() => {
        if (this.process) {
          this.process.removeListener('exit', onExit);
        }
        resolve(false);
      }, timeoutMs);

      this.process.once('exit', onExit);
    });
  }
}

module.exports = { DaemonLauncher };
