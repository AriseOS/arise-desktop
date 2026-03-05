# Arise

**The Work Companion Who Truly Knows You.**

Arise watches you work once, learns your methodology, and remembers it forever. Your workflows, your decisions, your shortcuts — encoded into a living memory that grows with you, every single day.

Most AI forgets you the moment the conversation ends. Arise is different — it encodes your methodology, the way you navigate tools, the order you make decisions, the shortcuts only you know — and carries that understanding forward, always.

## How It Works

1. **Work Once** — Just do your work as usual. Arise observes and distills the methodology behind your actions — not just the clicks, but the intent.
2. **Say the Word** — Next time, just describe what you need. Arise retrieves the right methodology from its memory and builds an execution plan.
3. **It's Done** — Arise works the way you would — same decisions, same quality. Review, approve, and reclaim your time for work that matters.

## What Makes Arise Different

- **Encodes Your Methodology** — Not a recording — a deep understanding. Arise extracts the logic behind your actions: why you clicked there, what you checked first, how you decided.
- **Maps Your Work World** — Every tool you use, every platform you navigate, every decision pattern you follow — Arise builds a living knowledge graph of your entire operational landscape.
- **Executes Like You Would** — When Arise automates a task, it doesn't just follow steps — it works the way you work. Same tools, same logic, same quality.
- **Evolves With You** — Change how you work, and Arise adapts. Every execution refines its understanding, discovers better paths, and builds on what it already knows.

## Tech Stack

- **Frontend**: React 18 + Vite + Zustand
- **Desktop Runtime**: Electron 33
- **Backend Daemon**: Node.js + Express + TypeScript
- **Browser Automation**: Playwright (connects to Electron's Chromium via CDP)
- **Memory**: Five-layer cognitive memory system (sensory, working, episodic, semantic, procedural)

## Development

### Prerequisites

- Node.js 18+
- npm

### Setup

```bash
npm install
cd daemon-ts && npm install
```

### Run

```bash
# Quick start (macOS)
./scripts/run_desktop_app.sh

# Or manually
npm run electron:dev
```

### Build

```bash
# macOS
./scripts/build_app_macos.sh

# Windows (PowerShell)
.\scripts\build_app_windows.ps1
```

## Project Structure

```
arise-desktop/
├── electron/          # Electron main process
├── daemon-ts/         # TypeScript daemon (Express + Playwright)
├── src/               # React frontend
├── icons/             # App icons
├── scripts/           # Build and run scripts
├── docs/              # Design documents
├── package.json       # Frontend manifest
├── electron-builder.json
├── vite.config.js
└── index.html
```

## Learn More

Visit [ariseos.com](https://ariseos.com) to explore the full Arise platform — Agent App, Memory Service, and Memory Database.
