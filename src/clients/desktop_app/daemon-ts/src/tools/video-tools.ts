/**
 * Video Tools — Video download and info via yt-dlp.
 *
 * Ported from video_downloader_toolkit.py.
 *
 * Tools: download_video, get_video_info, download_audio.
 *
 * Dependencies: yt-dlp CLI (must be installed on system).
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { execFile } from "node:child_process";
import { resolve, join } from "node:path";
import { mkdir } from "node:fs/promises";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("video-tools");

// ===== Helpers =====

function runYtDlp(
  args: string[],
  cwd: string,
  timeoutMs = 300_000,
): Promise<{ stdout: string; stderr: string; exitCode: number | null }> {
  return new Promise((resolve, reject) => {
    execFile("yt-dlp", args, { cwd, timeout: timeoutMs, maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err && (err as any).killed) {
        reject(new Error(`yt-dlp timed out after ${timeoutMs / 1000}s`));
        return;
      }
      resolve({
        stdout: stdout ?? "",
        stderr: stderr ?? "",
        exitCode: err ? (err as any).code ?? 1 : 0,
      });
    });
  });
}

/** Sanitize filename to prevent path traversal */
function sanitizeFilename(name: string): string {
  return name.replace(/[/\\:*?"<>|]/g, "_").replace(/\.\./g, "_");
}

function resolvePath(filename: string, workingDir: string): string {
  let resolved: string;
  if (filename.startsWith("/") || filename.startsWith("~")) {
    resolved = resolve(filename.replace(/^~/, process.env.HOME ?? "/tmp"));
  } else {
    resolved = resolve(workingDir, filename);
  }
  const normalizedWorkingDir = resolve(workingDir);
  if (!resolved.startsWith(normalizedWorkingDir + "/") && resolved !== normalizedWorkingDir) {
    throw new Error(`Path traversal detected: "${filename}" resolves outside working directory`);
  }
  return resolved;
}

// ===== Schemas =====

const downloadVideoSchema = Type.Object({
  url: Type.String({ description: "URL of the video to download" }),
  output_name: Type.Optional(
    Type.String({ description: "Output filename (without extension)" }),
  ),
});

const videoInfoSchema = Type.Object({
  url: Type.String({ description: "URL of the video" }),
});

const downloadAudioSchema = Type.Object({
  url: Type.String({ description: "URL of the video to extract audio from" }),
  output_name: Type.Optional(
    Type.String({ description: "Output filename (without extension)" }),
  ),
});

// ===== Tool Factory =====

export function createVideoTools(opts: {
  workingDir: string;
}): AgentTool<any>[] {
  const { workingDir } = opts;

  const download_video: AgentTool<typeof downloadVideoSchema> = {
    name: "download_video",
    label: "Download Video",
    description:
      "Download a video from a URL using yt-dlp. Supports YouTube, Twitter, TikTok, and most video platforms.",
    parameters: downloadVideoSchema,
    execute: async (_id, params) => {
      const outputName = sanitizeFilename(params.output_name ?? `video_${Date.now()}`);
      const outputPath = join(workingDir, `${outputName}.%(ext)s`);

      await mkdir(workingDir, { recursive: true });

      logger.info({ url: params.url, outputName }, "Downloading video");

      const result = await runYtDlp(
        ["-o", outputPath, "--no-playlist", params.url],
        workingDir,
      );

      if (result.exitCode !== 0) {
        throw new Error(
          `yt-dlp failed (exit ${result.exitCode}): ${result.stderr.slice(0, 500)}`,
        );
      }

      // Extract filename from output
      const filenameMatch = result.stdout.match(
        /\[download\] Destination: (.+)/,
      );
      const mergeMatch = result.stdout.match(
        /\[Merger\] Merging formats into "(.+)"/,
      );
      const downloadedFile =
        mergeMatch?.[1] ?? filenameMatch?.[1] ?? `${outputName}.(unknown)`;

      return {
        content: [
          {
            type: "text",
            text: `Video downloaded: ${downloadedFile}`,
          },
        ],
        details: undefined,
      };
    },
  };

  const get_video_info: AgentTool<typeof videoInfoSchema> = {
    name: "get_video_info",
    label: "Get Video Info",
    description:
      "Get metadata about a video (title, duration, resolution, etc.) without downloading.",
    parameters: videoInfoSchema,
    execute: async (_id, params) => {
      logger.info({ url: params.url }, "Getting video info");

      const result = await runYtDlp(
        ["--dump-json", "--no-download", params.url],
        workingDir,
        30_000,
      );

      if (result.exitCode !== 0) {
        throw new Error(
          `yt-dlp failed: ${result.stderr.slice(0, 500)}`,
        );
      }

      try {
        const info = JSON.parse(result.stdout);
        const summary = [
          `Title: ${info.title ?? "Unknown"}`,
          `Duration: ${info.duration ? `${Math.floor(info.duration / 60)}m ${info.duration % 60}s` : "Unknown"}`,
          `Resolution: ${info.width ?? "?"}x${info.height ?? "?"}`,
          `Uploader: ${info.uploader ?? "Unknown"}`,
          `Upload Date: ${info.upload_date ?? "Unknown"}`,
          `View Count: ${info.view_count ?? "Unknown"}`,
          `Description: ${(info.description ?? "").slice(0, 500)}`,
        ].join("\n");

        return {
          content: [{ type: "text", text: summary }],
          details: undefined,
        };
      } catch {
        return {
          content: [
            { type: "text", text: result.stdout.slice(0, 2000) },
          ],
          details: undefined,
        };
      }
    },
  };

  const download_audio: AgentTool<typeof downloadAudioSchema> = {
    name: "download_audio",
    label: "Download Audio",
    description:
      "Extract and download audio from a video URL. Output as mp3.",
    parameters: downloadAudioSchema,
    execute: async (_id, params) => {
      const outputName = sanitizeFilename(params.output_name ?? `audio_${Date.now()}`);
      const outputPath = join(workingDir, `${outputName}.%(ext)s`);

      await mkdir(workingDir, { recursive: true });

      logger.info({ url: params.url }, "Downloading audio");

      const result = await runYtDlp(
        ["-x", "--audio-format", "mp3", "-o", outputPath, "--no-playlist", params.url],
        workingDir,
      );

      if (result.exitCode !== 0) {
        throw new Error(
          `yt-dlp failed (exit ${result.exitCode}): ${result.stderr.slice(0, 500)}`,
        );
      }

      return {
        content: [
          {
            type: "text",
            text: `Audio downloaded: ${outputName}.mp3`,
          },
        ],
        details: undefined,
      };
    },
  };

  return [download_video, get_video_info, download_audio];
}
