/**
 * Search Tools — Web search via Google Custom Search API + DuckDuckGo fallback.
 *
 * Ported from search_toolkit.py.
 */

import { Type, type Static } from "@sinclair/typebox";
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { createLogger } from "../utils/logging.js";

const logger = createLogger("search-tools");

// ===== Schema =====

const searchSchema = Type.Object({
  query: Type.String({ description: "Search query string" }),
  num_results: Type.Optional(
    Type.Number({ description: "Number of results to return (default 10, max 20)" }),
  ),
});

// ===== Search Result =====

interface SearchResult {
  title: string;
  url: string;
  snippet: string;
}

// ===== Google Custom Search =====

async function searchGoogleAPI(
  query: string,
  numResults: number,
  apiKey: string,
  searchEngineId: string,
): Promise<SearchResult[]> {
  const results: SearchResult[] = [];
  const maxPerPage = 10;
  let start = 1;

  while (results.length < numResults) {
    const num = Math.min(maxPerPage, numResults - results.length);
    const url = new URL("https://www.googleapis.com/customsearch/v1");
    url.searchParams.set("key", apiKey);
    url.searchParams.set("cx", searchEngineId);
    url.searchParams.set("q", query);
    url.searchParams.set("num", String(num));
    url.searchParams.set("start", String(start));

    const resp = await fetch(url.toString(), { signal: AbortSignal.timeout(15_000) });
    if (!resp.ok) {
      logger.warn({ status: resp.status }, "Google API error, falling back to DuckDuckGo");
      return [];
    }

    const data = (await resp.json()) as { items?: { title: string; link: string; snippet?: string }[] };
    if (!data.items || data.items.length === 0) break;

    for (const item of data.items) {
      results.push({
        title: item.title,
        url: item.link,
        snippet: item.snippet ?? "",
      });
    }

    start += num;
    if (data.items.length < num) break;
  }

  return results;
}

// ===== DuckDuckGo HTML Fallback =====

async function searchDuckDuckGo(
  query: string,
  numResults: number,
): Promise<SearchResult[]> {
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  const resp = await fetch(url, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    },
    signal: AbortSignal.timeout(15_000),
  });

  if (!resp.ok) {
    throw new Error(`DuckDuckGo search failed: ${resp.status}`);
  }

  const html = await resp.text();
  const results: SearchResult[] = [];

  // Parse results from HTML (simple regex extraction)
  const resultPattern =
    /<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]*)<\/a>/gi;
  const snippetPattern =
    /<a[^>]+class="result__snippet"[^>]*>([\s\S]*?)<\/a>/gi;

  const urls: string[] = [];
  const titles: string[] = [];
  let match: RegExpExecArray | null;

  while ((match = resultPattern.exec(html)) !== null) {
    // DuckDuckGo wraps URLs in redirect: extract actual URL
    let href = match[1];
    const uddgMatch = href.match(/[?&]uddg=([^&]+)/);
    if (uddgMatch) {
      href = decodeURIComponent(uddgMatch[1]);
    }
    urls.push(href);
    titles.push(match[2].replace(/<[^>]+>/g, "").trim());
  }

  const snippets: string[] = [];
  while ((match = snippetPattern.exec(html)) !== null) {
    snippets.push(match[1].replace(/<[^>]+>/g, "").trim());
  }

  for (let i = 0; i < Math.min(urls.length, numResults); i++) {
    results.push({
      title: titles[i] ?? "",
      url: urls[i],
      snippet: snippets[i] ?? "",
    });
  }

  return results;
}

// ===== Format Results =====

function formatResults(results: SearchResult[], query: string): string {
  if (results.length === 0) {
    return `No results found for: "${query}"`;
  }

  const lines = [`Search results for: "${query}"\n`];
  for (let i = 0; i < results.length; i++) {
    const r = results[i];
    lines.push(`${i + 1}. ${r.title}`);
    lines.push(`   URL: ${r.url}`);
    if (r.snippet) {
      lines.push(`   ${r.snippet}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

// ===== Tool Factory =====

export function createSearchTools(): AgentTool<any>[] {
  const googleApiKey = process.env.GOOGLE_API_KEY;
  const searchEngineId = process.env.SEARCH_ENGINE_ID;
  const hasGoogleAPI = !!(googleApiKey && searchEngineId);

  const search_google: AgentTool<typeof searchSchema> = {
    name: "search_google",
    label: "Web Search",
    description:
      "Search the web using Google (or DuckDuckGo fallback). Returns titles, URLs, and snippets.",
    parameters: searchSchema,
    execute: async (_id, params) => {
      const query = params.query;
      const numResults = Math.min(params.num_results ?? 10, 20);

      logger.info({ query, numResults, hasGoogleAPI }, "Searching");

      let results: SearchResult[] = [];

      if (hasGoogleAPI) {
        results = await searchGoogleAPI(
          query,
          numResults,
          googleApiKey!,
          searchEngineId!,
        );
      }

      // Fallback to DuckDuckGo if Google returned nothing
      if (results.length === 0) {
        results = await searchDuckDuckGo(query, numResults);
      }

      const text = formatResults(results, query);

      return {
        content: [{ type: "text", text }],
        details: undefined,
      };
    },
  };

  return [search_google];
}
