import { Router, type Request, type Response } from "express";
import { getCloudClient, type RequestCredentials } from "../services/cloud-client.js";
import { siteTaskBatchService } from "../services/site-task-batch-service.js";

export const siteTasksRouter = Router();

function getCredentials(req: Request): RequestCredentials {
  const authHeader = req.headers.authorization;
  const token = authHeader?.startsWith("Bearer ") ? authHeader.slice(7) : undefined;
  return { token };
}

function getErrorStatus(err: unknown): number {
  if (err instanceof Error) {
    const match = err.message.match(/Cloud API error (\d{3})/);
    if (match) return parseInt(match[1], 10);
  }
  return 500;
}

siteTasksRouter.post("/generate-execute", async (req: Request, res: Response) => {
  const { sites, continue_on_error } = req.body ?? {};

  if (!Array.isArray(sites) || sites.length === 0 || !sites.every((item) => typeof item === "string" && item.trim())) {
    res.status(400).json({ error: "sites must be a non-empty string array" });
    return;
  }

  try {
    const client = getCloudClient();
    const creds = getCredentials(req);
    const generated = await client.generateSiteTasks(
      { sites: sites.map((item: string) => item.trim()) },
      creds,
    );
    const plans = Array.isArray(generated.results) ? generated.results : [];
    const batch = siteTaskBatchService.createBatch(plans, {
      continueOnError: continue_on_error !== false,
    });

    res.status(202).json({
      success: true,
      batch,
    });
  } catch (err) {
    res.status(getErrorStatus(err)).json({ error: String(err) });
  }
});

siteTasksRouter.get("/batches/:batchId", (req: Request, res: Response) => {
  const batch = siteTaskBatchService.getBatch(req.params.batchId);
  if (!batch) {
    res.status(404).json({ error: `Batch ${req.params.batchId} not found` });
    return;
  }

  res.json({
    success: true,
    batch,
  });
});
