/**
 * Image Tools — Image generation (DALL-E / Grok) and analysis (Claude vision).
 *
 * Ported from image_gen_toolkit.py + image_analysis_toolkit.py.
 *
 * Tools: generate_image, create_artwork, describe_image, ask_about_image,
 *        extract_text, identify_objects.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { Agent } from "@mariozechner/pi-agent-core";
import { debugStreamSimple } from "../utils/agent-helpers.js";
import { getConfiguredModel } from "../utils/config.js";
import { resolve, basename, dirname } from "node:path";
import { writeFile, readFile, mkdir } from "node:fs/promises";
import type { SSEEmitter } from "../events/emitter.js";
import { Action } from "../events/types.js";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("image-tools");

// ===== Schemas =====

const generateImageSchema = Type.Object({
  prompt: Type.String({
    description: "Detailed description of the image to generate",
  }),
  image_name: Type.Optional(
    Type.String({ description: "Output filename (e.g., 'chart.png')" }),
  ),
  size: Type.Optional(
    Type.String({
      description:
        "Image size: '1024x1024', '1792x1024', '1024x1792'. Default: '1024x1024'",
    }),
  ),
  quality: Type.Optional(
    Type.String({
      description: "Quality: 'auto', 'low', 'medium', 'high', 'standard', 'hd'. Default: 'auto'",
    }),
  ),
});

const createArtworkSchema = Type.Object({
  prompt: Type.String({ description: "Description of the artwork to create" }),
  style: Type.Optional(
    Type.String({
      description:
        "Art style (e.g., 'digital art', 'oil painting', 'watercolor', 'acrylic'). Default: 'digital art'",
    }),
  ),
  image_name: Type.Optional(
    Type.String({ description: "Output filename (must end with .png). Default: 'artwork.png'" }),
  ),
});

const describeImageSchema = Type.Object({
  image_path: Type.String({ description: "Path to the image file to analyze" }),
  question: Type.Optional(
    Type.String({
      description: "Specific question about the image. Default: describe the image.",
    }),
  ),
});

const askAboutImageSchema = Type.Object({
  image_path: Type.String({ description: "Path to the image file or URL" }),
  question: Type.String({ description: "The question to ask about the image" }),
});

const extractTextSchema = Type.Object({
  image_path: Type.String({ description: "Path to the image file to extract text from" }),
});

const identifyObjectsSchema = Type.Object({
  image_path: Type.String({ description: "Path to the image file to identify objects in" }),
});

// ===== Helpers =====

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

// ===== Vision Helper =====

async function askVision(
  imagePath: string,
  question: string,
  workingDir: string,
  apiKey?: string,
): Promise<string> {
  const filepath = resolvePath(imagePath, workingDir);
  const imageBuffer = await readFile(filepath);
  const base64 = imageBuffer.toString("base64");

  const ext = filepath.toLowerCase().split(".").pop();
  const mimeMap: Record<string, string> = {
    png: "image/png",
    jpg: "image/jpeg",
    jpeg: "image/jpeg",
    gif: "image/gif",
    webp: "image/webp",
  };
  const mimeType = mimeMap[ext ?? ""] ?? "image/png";

  const model = getConfiguredModel();
  const agent = new Agent({
    initialState: {
      systemPrompt: "You are a helpful image analysis assistant.",
      model,
      tools: [],
      messages: [
        {
          role: "user" as const,
          content: [
            { type: "image" as const, data: base64, mimeType },
            { type: "text" as const, text: question },
          ],
          timestamp: Date.now(),
        },
      ],
      thinkingLevel: "off",
    },
    getApiKey: async (provider: string) => {
      if (provider === "anthropic") {
        return apiKey ?? process.env.ANTHROPIC_API_KEY;
      }
      return undefined;
    },
    streamFn: debugStreamSimple,
  });

  await agent.prompt("");

  const messages = agent.state.messages;
  const lastAssistant = [...messages]
    .reverse()
    .find((m: any) => m.role === "assistant");

  if (lastAssistant && "content" in lastAssistant) {
    return (lastAssistant.content as any[])
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text)
      .join("\n");
  }

  return "";
}

// ===== Tool Factory =====

export function createImageTools(opts: {
  workingDir: string;
  taskId: string;
  apiKey?: string;
  emitter?: SSEEmitter;
}): AgentTool<any>[] {
  const { workingDir, taskId, apiKey, emitter } = opts;

  const openaiApiKey = process.env.OPENAI_API_KEY;

  const generate_image: AgentTool<typeof generateImageSchema> = {
    name: "generate_image",
    label: "Generate Image",
    description:
      "Generate an image using AI (DALL-E). Provide a detailed prompt describing the desired image.",
    parameters: generateImageSchema,
    execute: async (_id, params) => {
      if (!openaiApiKey) {
        throw new Error(
          "OPENAI_API_KEY not set. Cannot generate images.",
        );
      }

      const imageName =
        params.image_name ?? `generated_${Date.now()}.png`;
      const filepath = resolvePath(imageName, workingDir);
      const size = params.size ?? "1024x1024";
      const quality = params.quality ?? "auto";

      logger.info(
        { prompt: params.prompt.slice(0, 100), size, quality },
        "Generating image",
      );

      // Call OpenAI Images API
      const resp = await fetch(
        "https://api.openai.com/v1/images/generations",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${openaiApiKey}`,
          },
          body: JSON.stringify({
            model: "gpt-image-1",
            prompt: params.prompt,
            n: 1,
            size,
            quality,
            response_format: "b64_json",
          }),
          signal: AbortSignal.timeout(120_000),
        },
      );

      if (!resp.ok) {
        const errText = await resp.text().catch(() => "");
        throw new Error(
          `Image generation failed (${resp.status}): ${errText}`,
        );
      }

      const data = (await resp.json()) as {
        data: { b64_json: string }[];
      };

      if (!data.data?.[0]?.b64_json) {
        throw new Error("No image data in response");
      }

      // Save image
      const imageBuffer = Buffer.from(data.data[0].b64_json, "base64");
      await mkdir(dirname(filepath), { recursive: true });
      await writeFile(filepath, imageBuffer);

      emitter?.emit({
        action: Action.write_file,
        task_id: taskId,
        file_path: filepath,
        file_name: basename(filepath),
        file_size: imageBuffer.length,
        mime_type: "image/png",
      });

      logger.info(
        { filepath, size: imageBuffer.length },
        "Image generated",
      );

      return {
        content: [
          {
            type: "text",
            text: `Image generated and saved: ${filepath} (${imageBuffer.length} bytes)`,
          },
        ],
        details: undefined,
      };
    },
  };

  const create_artwork: AgentTool<typeof createArtworkSchema> = {
    name: "create_artwork",
    label: "Create Artwork",
    description:
      "Create an artwork image with a specific art style. Wraps image generation with style enhancement.",
    parameters: createArtworkSchema,
    execute: async (_id, params) => {
      if (!openaiApiKey) {
        throw new Error("OPENAI_API_KEY not set. Cannot generate images.");
      }

      const imageName = params.image_name ?? "artwork.png";
      if (!imageName.endsWith(".png")) {
        return {
          content: [
            { type: "text", text: `Error: Image name must end with .png, got: ${imageName}` },
          ],
          details: undefined,
        };
      }

      const style = params.style ?? "digital art";
      const enhancedPrompt = `${params.prompt}, ${style} style, high quality, detailed`;
      const filepath = resolvePath(imageName, workingDir);
      const size = "1024x1024";

      logger.info({ prompt: enhancedPrompt.slice(0, 100), style }, "Creating artwork");

      const resp = await fetch("https://api.openai.com/v1/images/generations", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${openaiApiKey}`,
        },
        body: JSON.stringify({
          model: "gpt-image-1",
          prompt: enhancedPrompt,
          n: 1,
          size,
          quality: "high",
          response_format: "b64_json",
        }),
        signal: AbortSignal.timeout(120_000),
      });

      if (!resp.ok) {
        const errText = await resp.text().catch(() => "");
        throw new Error(`Artwork generation failed (${resp.status}): ${errText}`);
      }

      const data = (await resp.json()) as { data: { b64_json: string }[] };
      if (!data.data?.[0]?.b64_json) {
        throw new Error("No image data in response");
      }

      const imageBuffer = Buffer.from(data.data[0].b64_json, "base64");
      await mkdir(dirname(filepath), { recursive: true });
      await writeFile(filepath, imageBuffer);

      emitter?.emit({
        action: Action.write_file,
        task_id: taskId,
        file_path: filepath,
        file_name: basename(filepath),
        file_size: imageBuffer.length,
        mime_type: "image/png",
      });

      return {
        content: [
          {
            type: "text",
            text: `Artwork created: ${filepath} (${style} style, ${imageBuffer.length} bytes)`,
          },
        ],
        details: undefined,
      };
    },
  };

  const describe_image: AgentTool<typeof describeImageSchema> = {
    name: "describe_image",
    label: "Describe Image",
    description:
      "Describe an image in detail using AI vision.",
    parameters: describeImageSchema,
    execute: async (_id, params) => {
      const question = params.question ?? "Describe this image in detail.";
      logger.info({ image: params.image_path, question: question.slice(0, 100) }, "Describing image");

      const responseText = await askVision(params.image_path, question, workingDir, apiKey);

      return {
        content: [
          { type: "text", text: responseText || "No description generated." },
        ],
        details: undefined,
      };
    },
  };

  const ask_about_image: AgentTool<typeof askAboutImageSchema> = {
    name: "ask_about_image",
    label: "Ask About Image",
    description:
      "Ask a specific question about an image using AI vision.",
    parameters: askAboutImageSchema,
    execute: async (_id, params) => {
      logger.info(
        { image: params.image_path, question: params.question.slice(0, 100) },
        "Asking about image",
      );

      const responseText = await askVision(params.image_path, params.question, workingDir, apiKey);

      return {
        content: [
          { type: "text", text: responseText || "Unable to answer based on the image." },
        ],
        details: undefined,
      };
    },
  };

  const extract_text: AgentTool<typeof extractTextSchema> = {
    name: "extract_text",
    label: "Extract Text from Image",
    description:
      "Extract and transcribe all visible text from an image (OCR). Includes text from signs, labels, documents, screens.",
    parameters: extractTextSchema,
    execute: async (_id, params) => {
      logger.info({ image: params.image_path }, "Extracting text from image");

      const responseText = await askVision(
        params.image_path,
        "Please extract and transcribe all text visible in this image. " +
          "Include text from signs, labels, documents, screens, or any other source. " +
          "Preserve the layout and formatting as much as possible.",
        workingDir,
        apiKey,
      );

      return {
        content: [
          { type: "text", text: responseText || "No text detected in the image." },
        ],
        details: undefined,
      };
    },
  };

  const identify_objects: AgentTool<typeof identifyObjectsSchema> = {
    name: "identify_objects",
    label: "Identify Objects",
    description:
      "Identify and list all distinct objects visible in an image with descriptions and locations.",
    parameters: identifyObjectsSchema,
    execute: async (_id, params) => {
      logger.info({ image: params.image_path }, "Identifying objects in image");

      const responseText = await askVision(
        params.image_path,
        "Please identify and list all distinct objects visible in this image. " +
          "For each object, provide: 1) Name of the object, 2) Brief description, " +
          "3) Approximate location in the image (e.g., center, top-left). " +
          "Format as a numbered list.",
        workingDir,
        apiKey,
      );

      return {
        content: [
          { type: "text", text: responseText || "No objects identified." },
        ],
        details: undefined,
      };
    },
  };

  return [
    generate_image,
    create_artwork,
    describe_image,
    ask_about_image,
    extract_text,
    identify_objects,
  ];
}
