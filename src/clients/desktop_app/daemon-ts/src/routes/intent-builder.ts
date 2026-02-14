/**
 * Intent Builder Routes — Proxy to cloud backend intent builder API.
 *
 * POST   /api/v1/intent-builder/sessions               — create session
 * GET    /api/v1/intent-builder/sessions/:id/stream     — SSE stream
 * POST   /api/v1/intent-builder/sessions/:id/chat       — send message
 * GET    /api/v1/intent-builder/sessions/:id/state      — get state
 * DELETE /api/v1/intent-builder/sessions/:id            — delete session
 */

import { Router, type Request, type Response } from "express";
import { getCloudClient, type RequestCredentials } from "../services/cloud-client.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("intent-builder-routes");

export const intentBuilderRouter = Router();

function getCredentials(req: Request): RequestCredentials {
  return {
    apiKey: req.headers["x-ami-api-key"] as string | undefined,
    userId: req.headers["x-user-id"] as string | undefined,
  };
}

// ===== POST /sessions =====

intentBuilderRouter.post("/sessions", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const result = await client.createIntentBuilderSession(req.body, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /sessions/:sessionId/stream =====

intentBuilderRouter.get(
  "/sessions/:sessionId/stream",
  async (req: Request, res: Response) => {
    const { sessionId } = req.params;
    const creds = getCredentials(req);

    try {
      const client = getCloudClient();
      const upstream = await client.intentBuilderStream(sessionId, creds);

      if (!upstream.ok) {
        res.status(upstream.status).json({
          error: `Upstream error: ${upstream.status}`,
        });
        return;
      }

      // Set SSE headers
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
      });

      // Pipe upstream SSE to client
      const reader = upstream.body?.getReader();
      if (!reader) {
        res.end();
        return;
      }

      // Cancel upstream reader on client disconnect
      req.on("close", () => {
        reader.cancel().catch(() => {});
      });

      const decoder = new TextDecoder();

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value, { stream: true });
          res.write(text);
        }
      } catch {
        // Stream closed
      } finally {
        reader.cancel().catch(() => {});
        res.end();
      }
    } catch (err) {
      if (!res.headersSent) {
        res.status(500).json({ error: String(err) });
      } else {
        res.end();
      }
    }
  },
);

// ===== POST /sessions/:sessionId/chat =====

intentBuilderRouter.post(
  "/sessions/:sessionId/chat",
  async (req: Request, res: Response) => {
    try {
      const client = getCloudClient();
      const creds = getCredentials(req);
      const { message } = req.body;
      const result = await client.intentBuilderChat(
        req.params.sessionId,
        message,
        creds,
      );
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  },
);

// ===== GET /sessions/:sessionId/state =====

intentBuilderRouter.get(
  "/sessions/:sessionId/state",
  async (req: Request, res: Response) => {
    try {
      const client = getCloudClient();
      const creds = getCredentials(req);
      const result = await client.getIntentBuilderState(req.params.sessionId, creds);
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  },
);

// ===== DELETE /sessions/:sessionId =====

intentBuilderRouter.delete(
  "/sessions/:sessionId",
  async (req: Request, res: Response) => {
    try {
      const client = getCloudClient();
      const creds = getCredentials(req);
      const result = await client.deleteIntentBuilderSession(
        req.params.sessionId,
        creds,
      );
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  },
);
