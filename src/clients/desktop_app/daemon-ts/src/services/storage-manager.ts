/**
 * Storage Manager — Local file storage for recordings and snapshots.
 *
 * Ported from storage_manager.py.
 *
 * Directory structure:
 *   ~/.ami/users/{userId}/recordings/{sessionId}/
 *     recording.json    (metadata + operations)
 *     snapshots/
 *       {urlHash}.json  (page snapshots)
 */

import {
  mkdirSync,
  existsSync,
  rmSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { AMI_DIR } from "../utils/config.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("storage-manager");

// ===== Types =====

export interface RecordingMetadata {
  session_id: string;
  created_at: string;
  ended_at?: string;
  updated_at?: string;
  task_metadata?: {
    name?: string;
    description?: string;
    user_query?: string;
  };
  operations: Record<string, unknown>[];
}

export interface RecordingListItem {
  session_id: string;
  task_metadata?: Record<string, unknown>;
  created_at?: string;
  action_count: number;
  snapshot_count: number;
}

// ===== Storage Manager =====

export class StorageManager {
  private basePath: string;

  constructor(basePath?: string) {
    this.basePath = basePath ?? AMI_DIR;
  }

  // ===== Path Helpers =====

  private sanitizeId(id: string): string {
    return id.replace(/[/\\]/g, "_").replace(/\.\./g, "_");
  }

  private userPath(userId: string): string {
    const dir = join(this.basePath, "users", this.sanitizeId(userId));
    mkdirSync(dir, { recursive: true });
    return dir;
  }

  private recordingPath(userId: string, sessionId: string): string {
    return join(this.userPath(userId), "recordings", this.sanitizeId(sessionId));
  }

  private recordingFile(userId: string, sessionId: string): string {
    return join(this.recordingPath(userId, sessionId), "recording.json");
  }

  private snapshotsDir(userId: string, sessionId: string): string {
    return join(this.recordingPath(userId, sessionId), "snapshots");
  }

  // ===== Recording CRUD =====

  saveRecording(
    userId: string,
    sessionId: string,
    data: Record<string, unknown>,
    updateTimestamp = true,
  ): void {
    const dir = this.recordingPath(userId, sessionId);
    mkdirSync(dir, { recursive: true });

    if (updateTimestamp) {
      data.updated_at = new Date().toISOString();
    }

    const filepath = this.recordingFile(userId, sessionId);
    writeFileSync(filepath, JSON.stringify(data, null, 2), "utf-8");
    logger.debug({ filepath }, "Recording saved");
  }

  saveSnapshot(
    userId: string,
    sessionId: string,
    urlHash: string,
    snapshotData: Record<string, unknown>,
  ): void {
    const dir = this.snapshotsDir(userId, sessionId);
    mkdirSync(dir, { recursive: true });

    const filepath = join(dir, `${urlHash}.json`);
    writeFileSync(filepath, JSON.stringify(snapshotData, null, 2), "utf-8");
  }

  getRecording(
    userId: string,
    sessionId: string,
  ): Record<string, unknown> | null {
    const filepath = this.recordingFile(userId, sessionId);
    if (!existsSync(filepath)) return null;

    try {
      const data = JSON.parse(readFileSync(filepath, "utf-8"));

      // Load snapshots
      const snapshotsDir = this.snapshotsDir(userId, sessionId);
      if (existsSync(snapshotsDir)) {
        const snapshots: Record<string, unknown> = {};
        for (const file of readdirSync(snapshotsDir)) {
          if (file.endsWith(".json")) {
            const urlHash = file.replace(".json", "");
            try {
              snapshots[urlHash] = JSON.parse(
                readFileSync(join(snapshotsDir, file), "utf-8"),
              );
            } catch (snapErr) {
              logger.warn({ file, err: snapErr }, "Skipping corrupted snapshot file");
            }
          }
        }
        if (Object.keys(snapshots).length > 0) {
          data.snapshots = snapshots;
        }
      }

      return data;
    } catch (err) {
      logger.error({ err, filepath }, "Failed to read recording");
      return null;
    }
  }

  listRecordings(userId: string): RecordingListItem[] {
    const recordingsDir = join(this.userPath(userId), "recordings");
    if (!existsSync(recordingsDir)) return [];

    const items: RecordingListItem[] = [];

    for (const sessionId of readdirSync(recordingsDir)) {
      const filepath = this.recordingFile(userId, sessionId);
      if (!existsSync(filepath)) continue;

      try {
        const data = JSON.parse(readFileSync(filepath, "utf-8"));
        const snapshotsDir = this.snapshotsDir(userId, sessionId);
        const snapshotCount = existsSync(snapshotsDir)
          ? readdirSync(snapshotsDir).filter((f) => f.endsWith(".json")).length
          : 0;

        items.push({
          session_id: sessionId,
          task_metadata: data.task_metadata,
          created_at: data.created_at,
          action_count: data.operations?.length ?? 0,
          snapshot_count: snapshotCount,
        });
      } catch {
        // Skip invalid recordings
      }
    }

    // Sort by created_at descending (newest first)
    items.sort((a, b) =>
      (b.created_at ?? "").localeCompare(a.created_at ?? ""),
    );

    return items;
  }

  deleteRecording(userId: string, sessionId: string): boolean {
    const dir = this.recordingPath(userId, sessionId);
    if (!existsSync(dir)) return false;

    try {
      rmSync(dir, { recursive: true, force: true });
      logger.info({ userId, sessionId }, "Recording deleted");
      return true;
    } catch (err) {
      logger.error({ err, dir }, "Failed to delete recording");
      return false;
    }
  }

  getRecordingDetail(
    userId: string,
    sessionId: string,
  ): Record<string, unknown> | null {
    const data = this.getRecording(userId, sessionId);
    if (!data) return null;

    return {
      session_id: sessionId,
      created_at: data.created_at,
      updated_at: data.updated_at,
      action_count: (data.operations as unknown[])?.length ?? 0,
      task_metadata: data.task_metadata,
      operations: data.operations,
      snapshots: data.snapshots,
    };
  }

  // ===== Metadata Updates =====

  updateRecordingMetadata(
    userId: string,
    sessionId: string,
    updates: {
      name?: string;
      task_description?: string;
      user_query?: string;
    },
  ): boolean {
    const data = this.getRecording(userId, sessionId);
    if (!data) return false;

    const metadata = (data.task_metadata ?? {}) as Record<string, unknown>;
    if (updates.name) metadata.name = updates.name;
    if (updates.task_description) metadata.description = updates.task_description;
    if (updates.user_query) metadata.user_query = updates.user_query;
    data.task_metadata = metadata;

    // Remove snapshots from save (they're in separate files)
    const { snapshots: _, ...saveData } = data;
    this.saveRecording(userId, sessionId, saveData);
    return true;
  }
}

// ===== Singleton =====

let _storageManager: StorageManager | null = null;

export function getStorageManager(): StorageManager {
  if (!_storageManager) {
    _storageManager = new StorageManager();
  }
  return _storageManager;
}
