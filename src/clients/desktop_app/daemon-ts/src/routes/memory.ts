/**
 * Memory Routes — Proxy to cloud backend memory API.
 *
 * POST   /api/v1/memory/add
 * POST   /api/v1/memory/query
 * GET    /api/v1/memory/stats
 * DELETE /api/v1/memory
 * GET    /api/v1/memory/phrases
 * GET    /api/v1/memory/phrases/public
 * GET    /api/v1/memory/phrases/:phraseId
 * DELETE /api/v1/memory/phrases/:phraseId
 * POST   /api/v1/memory/publish
 * POST   /api/v1/memory/unpublish
 * GET    /api/v1/memory/publish-status
 */

import { Router, type Request, type Response } from "express";
import { getCloudClient, type RequestCredentials } from "../services/cloud-client.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("memory-routes");

export const memoryRouter = Router();

// ===== Helper: extract per-request credentials =====

function getCredentials(req: Request): RequestCredentials {
  return {
    apiKey: req.headers["x-ami-api-key"] as string | undefined,
    userId: req.headers["x-user-id"] as string | undefined,
  };
}

// ===== POST /add =====

memoryRouter.post("/add", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const result = await client.memoryAdd(req.body, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== POST /query =====

memoryRouter.post("/query", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const result = await client.memoryQuery(req.body, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /stats =====

memoryRouter.get("/stats", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const result = await client.memoryStats(creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /debug =====

memoryRouter.get("/debug", (_req: Request, res: Response) => {
  res.json({
    success: false,
    error: "Debug not available in proxy mode",
  });
});

// ===== DELETE / =====

memoryRouter.delete("/", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const result = await client.memoryDelete(creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /phrases =====

memoryRouter.get("/phrases", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const limit = parseInt(req.query.limit as string) || 50;
    const result = await client.listPhrases(limit, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /phrases/public =====

memoryRouter.get("/phrases/public", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const limit = parseInt(req.query.limit as string) || 50;
    const sort = (req.query.sort as string) ?? "popular";
    const result = await client.listPublicPhrases(limit, sort, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /phrases/:phraseId =====

memoryRouter.get("/phrases/:phraseId", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const source = req.query.source as string | undefined;
    const result = await client.getPhrase(req.params.phraseId, source, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== DELETE /phrases/:phraseId =====

memoryRouter.delete(
  "/phrases/:phraseId",
  async (req: Request, res: Response) => {
    try {
      const client = getCloudClient();
      const creds = getCredentials(req);
      const result = await client.deletePhrase(req.params.phraseId, creds);
      res.json(result);
    } catch (err) {
      res.status(500).json({ error: String(err) });
    }
  },
);

// ===== POST /publish =====

memoryRouter.post("/publish", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const { phrase_id } = req.body;
    const result = await client.publishPhrase(phrase_id, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== POST /unpublish =====

memoryRouter.post("/unpublish", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const { phrase_id } = req.body;
    const result = await client.unpublishPhrase(phrase_id, creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});

// ===== GET /publish-status =====

memoryRouter.get("/publish-status", async (req: Request, res: Response) => {
  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const result = await client.getPublishStatus(creds);
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: String(err) });
  }
});
