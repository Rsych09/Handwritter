---
name: headroom
description: AI agent context optimization, CCR (Compress-Cache-Retrieve), token reduction, proxy orchestration, and cross-agent memory. Use when optimizing context windows, compressing tool outputs/logs/code search, retrieving cached original content, monitoring token savings, or configuring Headroom MCP/proxy for Antigravity.
argument-hint: "[compress|retrieve|proxy|stats|learn|doctor] [args]"
metadata:
  author: headroomlabs-ai
  version: "1.0.0"
---

# Headroom — Context Optimization & Compression Layer

Headroom compresses everything an AI agent reads — tool outputs, logs, RAG chunks, files, and conversation history — before it reaches the LLM. It guarantees that models see compact, high-signal context while retaining the ability to retrieve full uncompressed content byte-for-byte on demand via CCR (Compress-Cache-Retrieve).

---

## When to Use

- **Context Window Pressure**: When handling massive terminal outputs, large test runs, git diffs, directory trees, or extensive log files.
- **Token Cost & Latency Reduction**: Minimizing prompt tokens (saving 20–60%+ on code search and up to 90%+ on repetitive logs/JSON) and trimming verbose output ceremonies.
- **CCR (Compress-Cache-Retrieve)**: Accessing original full content when a compressed summary contains a hash marker (`headroom_retrieve`).
- **Cross-Agent Memory & Learning**: Storing persistent session learnings, architectural conventions, and tuning verbosity via `headroom learn`.
- **MCP Tool Integration**: Running `headroom_compress`, `headroom_retrieve`, `headroom_stats` inside Antigravity and pair-programming agents.

---

## Architecture & How It Works

```
 Agent / Environment (Antigravity IDE, CLI, MCP Client)
         │  prompts · tool outputs · logs · files
         ▼
 ┌─────────────────────────────────────────────────────────┐
 │ Headroom (Local Execution — Zero Data Exfiltration)     │
 │ ─────────────────────────────────────────────────────── │
 │ CacheAligner   →  ContentRouter   →  CCR Storage        │
 │                     ├─ SmartCrusher   (JSON / Arrays)   │
 │                     ├─ CodeCompressor (AST / Code)      │
 │                     └─ Kompress-v2    (Logs / Text)     │
 │                                                         │
 │ Cross-Agent Memory · MCP Server (`headroom mcp serve`)  │
 └─────────────────────────────────────────────────────────┘
         │  compressed context + retrieval hash pointers
         ▼
 LLM Provider (Anthropic / OpenAI / Gemini / Bedrock)
```

1. **ContentRouter**: Detects content type and dispatches to specialized compressors.
2. **SmartCrusher**: Compresses repetitive JSON structures and tables without losing keys.
3. **CodeCompressor**: AST-aware code compression retaining signatures, types, and logic bodies.
4. **CCR**: Automatically caches full originals on disk (`~/.headroom/cache`) and supplies hash references (`[headroom:hash:...]`) that the agent can expand anytime.
5. **Output Shaper**: Verbosity steering and thinking effort routing to decrease generated token overhead.

---

## Quick Reference CLI Commands

### 1. Diagnostics & Health Check
```bash
# Verify installation, proxy connectivity, and agent configurations
headroom doctor

# Check performance and latency
headroom perf
```

### 2. Running the Local Proxy
```bash
# Start the local compression proxy on port 8787
headroom proxy --port 8787

# Enable output token reduction (verbosity steering & effort routing)
export HEADROOM_OUTPUT_SHAPER=1
headroom proxy --port 8787
```

### 3. MCP Integration
```bash
# Register Headroom MCP server into Antigravity IDE and other detected agents
headroom mcp install

# Or specifically for Antigravity
headroom mcp install --agent antigravity

# Run standalone MCP stdio server
headroom mcp serve
```

### 4. Live Dashboard & Savings
```bash
# Launch real-time web dashboard showing tokens saved, compression ratio, and cache stats
headroom dashboard

# CLI summary of token savings
headroom savings
headroom output-savings
```

### 5. Cross-Agent Learning & Memory
```bash
# Mine session history for mistakes, conventions, and learnings
headroom learn

# Analyze and apply optimal verbosity level based on user interaction patterns
headroom learn --verbosity --apply
```

---

## Antigravity IDE Integration

### MCP Server Registration
Headroom registers in Antigravity's authoritative global configuration (`~/.gemini/config/mcp_config.json`):

```json
{
  "mcpServers": {
    "headroom": {
      "command": "headroom",
      "args": ["mcp", "serve"],
      "env": {
        "HEADROOM_PROXY_URL": "http://127.0.0.1:8787"
      }
    }
  }
}
```

### Exposed MCP Tools

| Tool | Purpose | Parameters |
|---|---|---|
| `headroom_compress` | Manually compress arbitrary string content / tool output | `content` (str), `level` (optional) |
| `headroom_retrieve` | Expand a compressed hash reference back into the exact original text | `hash` (str) |
| `headroom_stats` | Inspect session compression metrics, hit rates, and tokens saved | None |
| `memory_search` | Query cross-session knowledge base for conventions and past decisions | `query` (str) |
| `memory_save` | Persist key facts, decisions, or user preferences into local memory | `key` (str), `value` (str) |

---

## Python Inline Usage

```python
from headroom import compress

# Compress conversation messages or large tool output
messages = [
    {"role": "system", "content": "You are a senior developer."},
    {"role": "user", "content": "Analyze the build logs: " + raw_logs}
]

result = compress(messages, model="gemini-2.0-flash")
print(f"Compressed {result.original_tokens} -> {result.compressed_tokens} tokens")
print(f"Tokens saved: {result.tokens_saved} ({result.compression_ratio:.1%})")
```
