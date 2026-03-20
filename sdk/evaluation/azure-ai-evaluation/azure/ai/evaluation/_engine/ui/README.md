# Evee Results Viewer

Interactive UI for viewing and comparing experiment results across multiple model runs.

## Overview

The Results Viewer is a standalone React-based web application that provides:

- **Side-by-side comparison** of model runs in an MLflow-style table
- **Baseline selection** with delta indicators
- **Model grouping** by name with visual separators
- **Drill-down view** for inspecting individual records
- **Metric toggles** for customizing the display

## Usage

The Results Viewer can be used in multiple ways:

### 1. Via CLI Command

```bash
evee view experiment/output/my_exp_v1.0__2026-01-29_12-00-00
```

This starts a local server and opens the viewer in your browser.

### 2. Via MCP Server

When using an MCP-compatible client (like VS Code with MCP Apps), the `view_results` tool automatically displays this UI.

### 3. Future Integrations

This UI component is designed to be reusable for future Evee dashboard or tracking features.

## Development

### Setup

```bash
npm install
```

### Build

```bash
npm run build
```

This creates a single-file HTML build at `dist/index.html` with all JavaScript and CSS inlined.

### Development Mode

```bash
npm run dev
```

Watches for changes and rebuilds automatically.

## Architecture

- **app.tsx**: Main React application
- **index.html**: Entry point HTML template
- **dist/index.html**: Built single-file output (served by both CLI and MCP)
- **vite.config.ts**: Build configuration using vite-plugin-singlefile

The app supports two data loading modes:

1. **MCP Mode**: Receives data via `ontoolresult` callback
2. **Standalone Mode**: Reads `window.__EVEE_RESULTS_DATA__` injected by CLI

## Technologies

- React 19
- TypeScript
- Vite (build tool)
- MCP Apps SDK (for MCP integration)
