/**
 * Browser Routes — Browser status and window management.
 *
 * GET  /api/v1/browser/status          — connection status
 * GET  /api/v1/browser/window/layout   — window layout info
 * POST /api/v1/browser/window/update   — update window position
 */

import { Router, type Request, type Response } from "express";
import { BrowserSession } from "../browser/browser-session.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("browser-routes");

export const browserRouter = Router();

// ===== GET /status =====

browserRouter.get("/status", async (_req: Request, res: Response) => {
  const cdpPort = process.env.BROWSER_CDP_PORT;

  if (!cdpPort) {
    res.json({
      connected: false,
      cdp_port: null,
      tabs: [],
    });
    return;
  }

  try {
    const session = BrowserSession.getInstance("default");
    const isConnected = session.isConnected;

    let tabs: Record<string, unknown>[] = [];
    if (isConnected) {
      const tabInfo = await session.getTabInfo();
      tabs = tabInfo.map((t) => ({
        id: t.tab_id,
        url: t.url,
        title: t.title,
        active: t.is_current,
      }));
    }

    res.json({
      connected: isConnected,
      cdp_port: parseInt(cdpPort),
      tabs,
    });
  } catch (err) {
    res.json({
      connected: false,
      cdp_port: parseInt(cdpPort),
      tabs: [],
      error: String(err),
    });
  }
});

// ===== GET /window/layout =====

browserRouter.get("/window/layout", (_req: Request, res: Response) => {
  // Window layout is managed by Electron, not the daemon
  res.json({
    message: "Window layout managed by Electron main process",
  });
});

// ===== POST /window/update =====

browserRouter.post("/window/update", (_req: Request, res: Response) => {
  // Window position is managed by Electron
  res.json({
    success: false,
    message: "Window position managed by Electron main process",
  });
});

