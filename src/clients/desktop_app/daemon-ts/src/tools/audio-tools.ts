/**
 * Audio Tools — Audio transcription and analysis.
 *
 * Ported from transcription_toolkit.py (AudioAnalysisToolkit).
 *
 * Tools: transcribe_audio, ask_about_audio, summarize_audio, identify_speakers.
 *
 * Dependencies: OpenAI Whisper API for transcription, Claude for reasoning.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { Agent } from "@mariozechner/pi-agent-core";
import { debugStreamSimple } from "../utils/agent-helpers.js";
import { getConfiguredModel } from "../utils/config.js";
import { readFile } from "node:fs/promises";
import { resolve, basename } from "node:path";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("audio-tools");

// ===== Schemas =====

const transcribeSchema = Type.Object({
  audio_path: Type.String({
    description: "Path to the audio file (mp3, wav, m4a, webm, etc.)",
  }),
});

const askAboutAudioSchema = Type.Object({
  audio_path: Type.String({ description: "Path to the audio file" }),
  question: Type.String({ description: "Question to ask about the audio content" }),
});

const summarizeAudioSchema = Type.Object({
  audio_path: Type.String({ description: "Path to the audio file to summarize" }),
});

const identifySpeakersSchema = Type.Object({
  audio_path: Type.String({ description: "Path to the audio file to analyze for speakers" }),
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

async function transcribeWithWhisper(filepath: string): Promise<string> {
  const openaiKey = process.env.OPENAI_API_KEY;
  if (!openaiKey) {
    throw new Error("OPENAI_API_KEY not set. Cannot transcribe audio.");
  }

  const audioBuffer = await readFile(filepath);
  const filename = basename(filepath);

  // Build form data
  const formData = new FormData();
  formData.append(
    "file",
    new Blob([audioBuffer], { type: "application/octet-stream" }),
    filename,
  );
  formData.append("model", "whisper-1");

  const resp = await fetch(
    "https://api.openai.com/v1/audio/transcriptions",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${openaiKey}`,
      },
      body: formData,
      signal: AbortSignal.timeout(120_000),
    },
  );

  if (!resp.ok) {
    const errText = await resp.text().catch(() => "");
    throw new Error(`Whisper API error (${resp.status}): ${errText}`);
  }

  const data = (await resp.json()) as { text: string };
  return data.text;
}

// ===== Transcribe + Ask Helper =====

async function transcribeAndAsk(
  audioPath: string,
  question: string,
  workingDir: string,
  apiKey?: string,
): Promise<string> {
  const filepath = resolvePath(audioPath, workingDir);
  const transcript = await transcribeWithWhisper(filepath);

  if (!transcript) {
    return "No speech detected in the audio file.";
  }

  const model = getConfiguredModel();
  const agent = new Agent({
    initialState: {
      systemPrompt:
        "You are a helpful assistant that answers questions about audio content based on its transcript.",
      model,
      tools: [],
      messages: [],
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

  await agent.prompt(
    `Audio transcript:\n---\n${transcript}\n---\n\nQuestion: ${question}`,
  );

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

export function createAudioTools(opts: {
  workingDir: string;
  apiKey?: string;
}): AgentTool<any>[] {
  const { workingDir, apiKey } = opts;

  const transcribe_audio: AgentTool<typeof transcribeSchema> = {
    name: "transcribe_audio",
    label: "Transcribe Audio",
    description:
      "Transcribe audio to text using Whisper. Supports mp3, wav, m4a, webm, and more.",
    parameters: transcribeSchema,
    execute: async (_id, params) => {
      const filepath = resolvePath(params.audio_path, workingDir);
      logger.info({ filepath }, "Transcribing audio");

      const text = await transcribeWithWhisper(filepath);

      return {
        content: [
          {
            type: "text",
            text: text || "(no speech detected)",
          },
        ],
        details: undefined,
      };
    },
  };

  const ask_about_audio: AgentTool<typeof askAboutAudioSchema> = {
    name: "ask_about_audio",
    label: "Ask About Audio",
    description:
      "Ask a question about audio content. First transcribes the audio, then uses AI to answer the question based on the transcript.",
    parameters: askAboutAudioSchema,
    execute: async (_id, params) => {
      logger.info(
        { audio: params.audio_path, question: params.question.slice(0, 100) },
        "Asking about audio",
      );

      const responseText = await transcribeAndAsk(
        params.audio_path,
        params.question,
        workingDir,
        apiKey,
      );

      return {
        content: [
          {
            type: "text",
            text: responseText || "Unable to answer based on the audio content.",
          },
        ],
        details: undefined,
      };
    },
  };

  const summarize_audio: AgentTool<typeof summarizeAudioSchema> = {
    name: "summarize_audio",
    label: "Summarize Audio",
    description:
      "Provide a comprehensive summary of audio content including main topics, key points, and conclusions.",
    parameters: summarizeAudioSchema,
    execute: async (_id, params) => {
      logger.info({ audio: params.audio_path }, "Summarizing audio");

      const responseText = await transcribeAndAsk(
        params.audio_path,
        "Please provide a comprehensive summary of this audio. " +
          "Include the main topics discussed, key points made, " +
          "and any important conclusions or takeaways.",
        workingDir,
        apiKey,
      );

      return {
        content: [
          {
            type: "text",
            text: responseText || "Unable to summarize the audio content.",
          },
        ],
        details: undefined,
      };
    },
  };

  const identify_speakers: AgentTool<typeof identifySpeakersSchema> = {
    name: "identify_speakers",
    label: "Identify Speakers",
    description:
      "Identify speakers in audio, describe voice characteristics, roles, and summarize what each speaker says.",
    parameters: identifySpeakersSchema,
    execute: async (_id, params) => {
      logger.info({ audio: params.audio_path }, "Identifying speakers");

      const responseText = await transcribeAndAsk(
        params.audio_path,
        "How many speakers are in this audio? " +
          "Please describe each speaker's voice characteristics, " +
          "their role in the conversation (if apparent), " +
          "and summarize what each speaker says.",
        workingDir,
        apiKey,
      );

      return {
        content: [
          {
            type: "text",
            text: responseText || "Unable to identify speakers in the audio.",
          },
        ],
        details: undefined,
      };
    },
  };

  return [transcribe_audio, ask_about_audio, summarize_audio, identify_speakers];
}
