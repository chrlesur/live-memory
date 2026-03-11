# 🧠 Live Memory — MCP Knowledge Live Memory Service

> **Shared working memory for collaborative AI agents**

[![Version](https://img.shields.io/badge/version-0.6.0-blue.svg)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)]()
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)]()

---

## 📋 Table of Contents

- [Concept](#-concept)
- [Architecture](#-architecture)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Getting Started](#-getting-started)
- [MCP Tools](#-mcp-tools)
- [Graph Bridge](#-graph-bridge--link-to-graph-memory)
- [Web Interface](#-web-interface)
- [MCP Integration](#-mcp-integration)
- [CLI and Shell](#-cli-and-shell)
- [Tests](#-tests)
- [Security](#-security)
- [Project Structure](#-project-structure)
- [Troubleshooting](#-troubleshooting)

---

## 🎯 Concept

**Live Memory** is an MCP (Model Context Protocol) server that provides **Memory Bank as a Service** for AI agents. Multiple agents collaborate on the same project by sharing a common working memory.

```
graph-memory  = LONG-TERM memory (documents → Knowledge Graph → Vector RAG)
live-memory   = WORKING memory (live notes → LLM → Structured Memory Bank)
```

### Two Complementary Modes

| Mode         | Description                                                       | Analogy                   |
| ------------ | ----------------------------------------------------------------- | -------------------------- |
| **🔴 Live** | Real-time notes (observations, decisions, todos...) append-only   | Shared whiteboard         |
| **📘 Bank** | LLM consolidation into structured Markdown files based on rules   | Structured project log    |

### Why Live Memory?

| Problem                                     | Live Memory Solution                                            |
| ------------------------------------------- | --------------------------------------------------------------- |
| Agents lose context between sessions        | `bank_read_all` → complete context in 1 call                    |
| Multi-agent collaboration is impossible     | Append-only notes, no conflicts, cross-visibility               |
| Manual consolidation is tedious             | LLM transforms raw notes into structured documentation          |
| Memory scattered in local files             | Central S3 point, accessible from everywhere                    |
| No link with long-term memory               | 🌉 Graph Bridge pushes the bank into a knowledge graph          |

### 🧠 Multi-agent Collaboration and Two-Level Memory Architecture

Recent research on LLM-based multi-agent systems ([Tran et al., 2025 — *Multi-Agent Collaboration Mechanisms: A Survey of LLMs*](https://arxiv.org/abs/2501.06322)) identifies **shared memory** as a fundamental component. In their formal framework, a multi-agent system is defined by **agents** (A), a **shared environment** (E), and **collaboration channels** (C). The authors emphasize that LLMs are inherently isolated algorithms, not designed to collaborate — they need a **shared memory infrastructure** to coordinate their actions.

Live Memory + Graph Memory directly implements this architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                  Shared Environment E                       │
│                                                             │
│  ┌──────────────────┐   LLM    ┌─────────────────────┐      │
│  │  🔴 Live         │ ──────► │  📘 Bank             │      │
│  │  Real-time notes │ consolid│  Structured working │      │
│  │  (append-only)   │  -ates  │  memory             │      │
│  └──────────────────┘         └──────────┬───────────┘      │
│                                          │                  │
│                                     graph_push              │
│                                     (MCP Streamable HTTP)               │
│                                          │                  │
│                               ┌──────────▼───────────┐      │
│                               │  🌐 Graph Memory     │      │
│                               │  Knowledge Graph     │      │
│                               │  (entities, relations│      │
│                               │   embeddings, RAG)   │      │
│                               └──────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

| Level | Service | Duration | Content | Usage |
|-------|---------|-------|---------|-------|
| **Working Memory** | Live Memory | Session / project | Raw notes + consolidated Markdown bank | Operational context, daily coordination |
| **Long-term Memory** | Graph Memory | Permanent | Entities + relations + vector embeddings | Searchable knowledge base in natural language |

**The Graph Bridge** (`graph_push`) is the collaboration channel between these two levels. Following the **late-stage collaboration** pattern described in literature (sharing consolidated outputs as inputs to another system), it transforms working documentation (Markdown) into structured knowledge (entities/relations graph).

**Why two levels?** One level is not enough:
- Working memory alone is **ephemeral** — it disappears when the project ends
- Knowledge graph alone is **too heavy** for quick daily notes
- The bridge between the two allows agents to **work fast** (live notes) while **capitalizing** knowledge (graph)

Specifically, agents can:
1. **Write quickly** without friction (live-memory, append-only, ~50ms)
2. **Automatically consolidate** via LLM into structured documentation (bank, ~15s)
3. **Persist knowledge** in a searchable graph (graph-memory, ~2min)
4. **Query the graph** in natural language to retrieve information from past projects

---

## 🏗️ Architecture

```
     Agent Cline        Agent Claude        Agent X
          │                   │                │
          └────────┬──────────┘                │
                   │                           │
                   ▼  MCP Protocol (Streamable HTTP)  ▼
          ┌────────────────────────────────────────┐
          │   Caddy WAF (Coraza CRS)               │
          │   Rate Limiting • TLS • OWASP CRS      │
          └────────────┬───────────────────────────┘
                       │
          ┌────────────┴───────────────────┐
          │   Live Memory MCP (:8002)      │
          │   32 tools • Auth Bearer       │
          │   LLM Consolidation            │
          └──────┬──────────┬──────┬───────┘
                 │          │      │
          ┌──────┴──┐  ┌────┴───┐  │
          │   S3    │  │ LLMaaS │  │  MCP Streamable HTTP
          │Dell ECS │  │ CT API │  │  (optional)
          └─────────┘  └────────┘  │
                       ┌───────────┴────────────┐
                       │   Graph Memory         │
                       │   (long-term memory)   │
                       │   Neo4j + Qdrant       │
                       └────────────────────────┘
```

**Minimal Stack**: S3 + LLM. No local database.
**Optional**: connection to Graph Memory for long-term memory (knowledge graph).

---

## 📦 Prerequisites

- **Docker** >= 24.0 + **Docker Compose** v2
- **Python 3.11+** (for CLI, optional)
- A compatible **S3 storage** (Cloud Temple Dell ECS, AWS, MinIO)
- An OpenAI API compatible **LLM** (Cloud Temple LLMaaS, OpenAI, etc.)

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/chrlesur/live-memory.git
cd live-memory
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Edit `.env` with your values (see [Configuration](#-configuration)).

### 3a. Docker Start (recommended)

```bash
# Build images (WAF + MCP server)
docker compose build

# Start services
docker compose up -d

# Check status
docker compose ps

# Health check
curl -s http://localhost:8080/health
```

### 3b. Local Start (development)

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
cd src && python -m live_mem
```

### 4. Install CLI (optional)

```bash
pip install click rich prompt-toolkit mcp[cli]>=1.8.0
```

### 5. Verify Installation

```bash
# Health check via CLI
python scripts/mcp_cli.py health

# Or full E2E test (creates space, writes notes, consolidates)
python scripts/test_recette.py
```

### Exposed Ports

| Service    | Port   | Description                                |
| ---------- | ------ | ------------------------------------------ |
| **WAF**    | `8080` | Only exposed port — Caddy WAF → Live Memory |
| MCP Server | `8002` | Internal Docker network only               |

---

## ⚙️ Configuration

Edit `.env`. All variables are documented in `.env.example`.

### Mandatory Variables

| Variable               | Description              | Example                                      |
| ---------------------- | ------------------------ | -------------------------------------------- |
| `S3_ENDPOINT_URL`      | S3 endpoint URL          | `https://takinc5acc.s3.fr1.cloud-temple.com` |
| `S3_ACCESS_KEY_ID`     | S3 access key            | `AKIA...`                                    |
| `S3_SECRET_ACCESS_KEY` | S3 secret key            | `wJal...`                                    |
| `S3_BUCKET_NAME`       | Bucket name              | `live-mem`                                   |
| `S3_REGION_NAME`       | S3 region                | `fr1`                                        |
| `LLMAAS_API_URL`       | LLM API URL (with `/v1`) | `https://api.ai.cloud-temple.com/v1`         |
| `LLMAAS_API_KEY`       | LLM API key              | `sk-...`                                     |
| `ADMIN_BOOTSTRAP_KEY`  | Admin bootstrap key      | `my-secret-key-change-me`                   |

### Optional Variables

| Variable                  | Default           | Description                      |
| ------------------------- | ----------------- | -------------------------------- |
| `MCP_SERVER_PORT`         | `8002`            | MCP server listening port        |
| `MCP_SERVER_DEBUG`        | `false`           | Detailed logs                    |
| `LLMAAS_MODEL`            | `qwen3-2507:235b` | LLM model for consolidation      |
| `LLMAAS_MAX_TOKENS`       | `100000`          | Max tokens per LLM call          |
| `LLMAAS_TEMPERATURE`      | `0.3`             | LLM temperature                  |
| `CONSOLIDATION_TIMEOUT`   | `600`             | Consolidation timeout (seconds)  |
| `CONSOLIDATION_MAX_NOTES` | `500`             | Max notes per consolidation      |

---

## ▶️ Getting Started

```bash
docker compose up -d
docker compose ps       # Check status
docker compose logs -f live-mem-service --tail 50  # Logs
```

---

## 🔧 MCP Tools

32 tools exposed via the MCP protocol (Streamable HTTP), divided into 7 categories.

### System (2 tools)

| Tool            | Parameters | Description                                      |
| --------------- | ---------- | ------------------------------------------------ |
| `system_health` | —          | Health status (S3, LLMaaS, number of spaces)     |
| `system_about`  | —          | Service identity (version, tools, capabilities)  |

### Space (7 tools)

| Tool            | Parameters                                   | Description                                                |
| --------------- | -------------------------------------------- | ---------------------------------------------------------- |
| `space_create`  | `space_id`, `description`, `rules`, `owner?` | Creates a space with its rules (bank structure)            |
| `space_list`    | —                                            | Lists spaces accessible by current token                   |
| `space_info`    | `space_id`                                   | Detailed info (notes, bank, consolidation)                 |
| `space_rules`   | `space_id`                                   | Reads immutable space rules                                |
| `space_summary` | `space_id`                                   | Complete summary: rules + bank + stats (agent startup)     |
| `space_export`  | `space_id`                                   | tar.gz export in base64                                    |
| `space_delete`  | `space_id`, `confirm`                        | Deletes the space (⚠️ irreversible, admin required)        |

### Live (3 tools)

| Tool          | Parameters                                           | Description                                                                                            |
| ------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `live_note`   | `space_id`, `category`, `content`, `agent?`, `tags?` | Writes a timestamped note. Categories: observation, decision, todo, insight, question, progress, issue |
| `live_read`   | `space_id`, `limit?`, `category?`, `agent?`          | Reads live notes (optional filters)                                                                    |
| `live_search` | `space_id`, `query`, `limit?`                        | Full-text search in notes                                                                              |

### Bank (4 tools)

| Tool               | Parameters             | Description                                                                                                |
| ------------------ | ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| `bank_read`        | `space_id`, `filename` | Reads a specific bank file (e.g., `activeContext.md`)                                                      |
| `bank_read_all`    | `space_id`             | Reads entire bank in one request (🚀 agent startup)                                                        |
| `bank_list`        | `space_id`             | Lists bank files (without content)                                                                         |
| `bank_consolidate` | `space_id`, `agent?`   | 🧠 Consolidates notes via LLM. Empty `agent` = all notes (admin). `agent=name` = notes from this agent     |

### Graph (4 tools) — 🌉 Link to Graph Memory

| Tool               | Parameters                                           | Description                                                                                                  |
| ------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `graph_connect`    | `space_id`, `url`, `token`, `memory_id`, `ontology?` | Connects a space to Graph Memory. Tests connection, creates memory if needed. Default ontology: `general`    |
| `graph_push`       | `space_id`                                           | Synchronizes bank → graph. Smart delete + re-ingest, orphan cleanup. ~30s/file                               |
| `graph_status`     | `space_id`                                           | Connection status + graph stats (documents, entities, relations, top entities, documents list)               |
| `graph_disconnect` | `space_id`                                           | Disconnects (data remains in graph)                                                                          |

### Backup (5 tools)

| Tool              | Parameters                 | Description                                       |
| ----------------- | -------------------------- | ------------------------------------------------- |
| `backup_create`   | `space_id`, `description?` | Creates a full snapshot on S3                     |
| `backup_list`     | `space_id?`                | Lists available backups                           |
| `backup_restore`  | `backup_id`                | Restores a backup (space must not exist)          |
| `backup_download` | `backup_id`                | Download as tar.gz base64                         |
| `backup_delete`   | `backup_id`                | Deletes a backup                                  |

### Admin (7 tools)

| Tool                  | Parameters                                               | Description                                                                  |
| --------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `admin_create_token`  | `name`, `permissions`, `space_ids?`, `expires_in_days?`  | Creates a token (⚠️ displayed only once). Permissions: read, write, admin    |
| `admin_list_tokens`   | —                                                        | Lists active tokens                                                          |
| `admin_revoke_token`  | `token_hash`                                             | Revokes a token (makes it unusable)                                          |
| `admin_delete_token`  | `token_hash`                                             | Physically deletes a token from the registry (⚠️ irreversible)               |
| `admin_purge_tokens`  | `revoked_only?`                                          | Bulk purge: revoked only (default) or all tokens                             |
| `admin_update_token`  | `token_hash`, `space_ids`, `action`                      | Modifies token spaces (add/remove/set)                                       |
| `admin_gc_notes`      | `space_id?`, `max_age_days?`, `confirm?`, `delete_only?` | Garbage Collector: cleans orphaned notes                                     |

---

## 🌉 Graph Bridge — Link to Graph Memory

Live Memory can push its Memory Bank into a [Graph Memory](https://github.com/chrlesur/graph-memory) instance for long-term memory. The knowledge graph extracts entities, relations, and embeddings from bank files.

### Workflow

```
1. graph_connect(space_id, url, token, memory_id, ontology="general")
   └─ Tests connection, creates Graph Memory if needed

2. bank_consolidate(space_id)
   └─ LLM produces/updates bank files

3. graph_push(space_id)
   ├─ Lists documents in Graph Memory
   ├─ For each modified bank file:
   │   ├─ document_delete (removes orphaned entities)
   │   └─ memory_ingest (complete graph recalculation)
   ├─ Cleans deleted bank documents
   └─ Updates metrics (last_push, push_count)

4. graph_status(space_id)
   └─ Stats: 79 entities, 61 relations, top entities, documents...
```

### Smart Push (delete + re-ingest)

Each push is a **complete refresh** of the graph for that file. Existing files are deleted then re-ingested so Graph Memory recalculates entities, relations, and embeddings with up-to-date content.

### Available Ontologies

| Ontology           | Usage                                        |
| ------------------ | -------------------------------------------- |
| `general` (default)| Versatile: FAQ, specs, certifications, CSR   |
| `legal`            | Legal documents, contracts                   |
| `cloud`            | Cloud infrastructure, product sheets         |
| `managed-services` | Managed services, outsourcing                |
| `presales`         | Pre-sales, RFP/RFI, proposals                |

---

## 🖥️ Web Interface

Live Memory exposes a **web interface** on `/live` to visualize memory spaces in real-time.

### Access

```
http://localhost:8080/live
```

### Features

| Zone | Content |
|------|---------|
| **📊 Dashboard** (left) | Space info, consolidation (date + counters), live/bank stats, colored agents, categories with %, Markdown rules, Graph Memory |
| **🔴 Live Timeline** (top-right) | Live notes grouped by date (Today/Yesterday/date), cards with agent + category + Markdown |
| **📘 Bank Viewer** (bottom-right) | Consolidated file tabs, Markdown rendering with marked.js |

### Layout

```
┌──────────────┬────────────────────────────┐
│  📊 Dashboard│  🔴 Live Timeline          │
│  (info,      │  (auto-refresh, date group)│
│   agents,    ├────────────────────────────┤
│   rules...)  │  📘 Bank (Markdown tabs)   │
└──────────────┴────────────────────────────┘
```

### Smart Auto-refresh

- Configurable: 3s / 5s / 10s / 30s / manual
- **Anti-flicker**: only re-renders DOM if data has changed
- Pulsing green dot with last refresh timestamp
- Space selection → immediate loading (no button needed)

### REST API (5 endpoints)

| Endpoint | Description |
|----------|-------------|
| `GET /api/spaces` | List of spaces |
| `GET /api/space/{id}` | Complete info (meta + rules + stats + graph-memory) |
| `GET /api/live/{id}` | Live notes (filters: `?agent=`, `?category=`, `?limit=`) |
| `GET /api/bank/{id}` | Bank file list |
| `GET /api/bank/{id}/{filename}` | Bank file content |

`/api/*` endpoints require a Bearer Token. `/live` page and `/static/*` files are public.

---

## 🔌 MCP Integration

> 📖 **Full Guide**: See [GUIDE_INTEGRATION_CLINE.md](GUIDE_INTEGRATION_CLINE.md) for the step-by-step guide (Cline configuration, custom instructions, workflow, multi-agents, troubleshooting).

### With Cline (VS Code / VSCodium)

In Cline's MCP settings (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_YOUR_TOKEN"
      }
    }
  }
}
```

Then add a **`.clinerules/standard.memory.bank.md`** file in your project (or in global Custom Instructions):

```markdown
# Cline's Memory Bank — Live Memory MCP

My memory resets completely between sessions. I depend ENTIRELY on the Memory Bank
to understand the project and continue effectively.

## 🔌 Connection

My persistent memory is managed by the MCP server **Live Memory** (`live-memory`).

- **Space** : `my-project`
- **Agent** : `cline-dev`

## 📖 At the start of EVERY task (MANDATORY)

1. Call `space_rules("my-project")` to read the rules (bank structure)
2. Call `bank_read_all("my-project")` to load ALL context
3. Read carefully before starting work
4. Identify the current focus in `activeContext.md`

> ⚠️ NEVER start working without reading the bank.

## 📝 During work

Write frequent, atomic notes with `live_note`:

live_note(space_id="my-project", category="observation", content="...", agent="cline-dev")
live_note(space_id="my-project", category="decision", content="...", agent="cline-dev")
live_note(space_id="my-project", category="progress", content="...", agent="cline-dev")
live_note(space_id="my-project", category="issue", content="...", agent="cline-dev")
live_note(space_id="my-project", category="todo", content="...", agent="cline-dev")
live_note(space_id="my-project", category="insight", content="...", agent="cline-dev")

**Categories**:
- `observation` — Factual findings, command results
- `decision` — Technical choices and their justification
- `progress` — Advancement, what is completed
- `issue` — Problems encountered, bugs
- `todo` — Tasks identified to do
- `insight` — Learnings, patterns discovered
- `question` — Points to clarify, pending decisions

## 🧠 End of session

bank_consolidate(space_id="my-project", agent="cline-dev")

The LLM will consolidate notes by updating bank files according to the space rules.

## ⚠️ Imperative rules

1. **NEVER write directly to the bank** — only LLM consolidation does that
2. **Always pass `agent="cline-dev"`** in `live_note` and `bank_consolidate`
3. **Always pass `space_id="my-project"`** in all calls
4. **Write atomic notes** — 1 note = 1 fact, 1 decision, or 1 task
5. **Consolidate at end of session** — never leave without consolidating
6. **Read the bank at startup** — never work without context

## 📊 Useful commands

| Action                    | Command                                                                            |
| ------------------------- | ---------------------------------------------------------------------------------- |
| Read all context          | `bank_read_all("my-project")`                                                      |
| Read rules                | `space_rules("my-project")`                                                        |
| Write a note              | `live_note(space_id="my-project", category="...", content="...", agent="cline-dev")`|
| Consolidate               | `bank_consolidate(space_id="my-project", agent="cline-dev")`                       |
| See recent notes          | `live_read(space_id="my-project")`                                                 |
| See another agent's notes | `live_read(space_id="my-project", agent="claude-review")`                          |
| Space info                | `space_info("my-project")`                                                         |
```

> 💡 Replace `my-project` with your space_id and `cline-dev` with your agent name.

### With Claude Desktop

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_YOUR_TOKEN"
      }
    }
  }
}
```

### Via Python (MCP client)

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def example():
    headers = {"Authorization": "Bearer your_token"}
    async with streamablehttp_client("http://localhost:8080/mcp", headers=headers) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # Load all context
            result = await session.call_tool("bank_read_all", {
                "space_id": "my-project"
            })

            # Write a note
            await session.call_tool("live_note", {
                "space_id": "my-project",
                "category": "observation",
                "content": "Build passing in CI"
            })
```

---

## 💻 CLI and Shell

### CLI Installation

```bash
pip install click rich prompt-toolkit mcp[cli]>=1.8.0
export MCP_URL=http://localhost:8080
export MCP_TOKEN=your_token
```

### CLI Commands (Click)

```bash
python scripts/mcp_cli.py health
python scripts/mcp_cli.py about
python scripts/mcp_cli.py space list
python scripts/mcp_cli.py space create my-project --rules-file rules.md
python scripts/mcp_cli.py live note my-project observation "Build OK"
python scripts/mcp_cli.py bank consolidate my-project
python scripts/mcp_cli.py bank read-all my-project
python scripts/mcp_cli.py token create agent-cline read,write
python scripts/mcp_cli.py graph connect my-project URL TOKEN MEM-ID -o general
python scripts/mcp_cli.py graph push my-project
python scripts/mcp_cli.py graph status my-project
python scripts/mcp_cli.py graph disconnect my-project
```

### Interactive Shell

```bash
python scripts/mcp_cli.py shell
```

Autocomplete, history, Rich display. See [scripts/README.md](scripts/README.md) for full reference.

---

## 🧪 Tests

5 E2E test scripts, all with `--step` (step-by-step) and `--no-cleanup`.

```bash
docker compose up -d   # Prerequisite

# 1. Recipe: 1 agent, 12 notes, consolidation → 6 bank files
python scripts/test_recette.py

# 2. Multi-agents: 3 agents collaborating
python scripts/test_multi_agents.py

# 3. Garbage Collector
python scripts/test_gc.py

# 4. Graph Bridge: link to Graph Memory
python scripts/test_graph_bridge.py \
  --graph-url https://graph-mem.mcp.cloud-temple.app \
  --graph-token your_token

# 5. Quality: 28 tests covering all 7 tool categories
python scripts/test_qualite.py

# Step-by-step mode (Enter to proceed)
python scripts/test_recette.py --step --no-cleanup
```

---

## 🔒 Security

### Authentication

- **Bearer Token** mandatory on all MCP requests
- **Bootstrap key** to create the first admin token
- **SHA-256 Tokens** stored on S3 (never in clear text)
- **3 levels**: read, write, admin
- **Space scope**: a token can be limited to specific spaces

### WAF (Caddy + Coraza)

- **OWASP CRS**: SQL/XSS injection, path traversal, SSRF
- **Rate Limiting**: 200 MCP/min (Streamable HTTP)
- **Automatic TLS**: Let's Encrypt in production (`SITE_ADDRESS=domain.com`)
- **Non-root container**: `mcp` user

---

## 📂 Project Structure

```
live-memory/
├── src/live_mem/              # Source code (32 MCP tools + web interface)
│   ├── server.py              # FastMCP server + middlewares
│   ├── config.py              # pydantic-settings configuration
│   ├── auth/                  # Authentication
│   │   ├── middleware.py      #   Auth + Logging + StaticFiles
│   │   └── context.py         #   check_access, check_write, check_admin
│   ├── static/                # /live web interface
│   │   ├── live.html          #   SPA (Dashboard + Live + Bank)
│   │   ├── css/live.css       #   Styles (Cloud Temple theme)
│   │   ├── js/                #   7 JS modules (config, api, app, dashboard, timeline, bank, sidebar)
│   │   └── img/               #   Cloud Temple SVG Logo
│   ├── core/                  # Business services
│   │   ├── storage.py         #   S3 dual SigV2/SigV4 (Dell ECS)
│   │   ├── space.py           #   Memory spaces CRUD
│   │   ├── live.py            #   Live notes (append-only)
│   │   ├── consolidator.py    #   LLM Pipeline (4 steps)
│   │   ├── graph_bridge.py    #   🌉 Link to Graph Memory
│   │   ├── tokens.py          #   SHA-256 tokens management
│   │   ├── backup.py          #   S3 snapshots
│   │   ├── gc.py              #   Garbage Collector
│   │   ├── locks.py           #   asyncio locks per space
│   │   └── models.py          #   Pydantic models
│   └── tools/                 # MCP Tools (7 modules)
│       ├── system.py          #   2 tools (health, about)
│       ├── space.py           #   7 tools (spaces CRUD)
│       ├── live.py            #   3 tools (notes)
│       ├── bank.py            #   4 tools (bank + consolidation)
│       ├── graph.py           #   4 tools (Graph Bridge)
│       ├── backup.py          #   5 tools (snapshots)
│       └── admin.py           #   7 tools (tokens + GC + purge)
├── scripts/                   # CLI + Shell + Tests
├── waf/                       # Caddy + Coraza WAF
├── DESIGN/live-mem/           # 9 architecture documents
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── VERSION                    # 0.6.0
├── CHANGELOG.md
└── FAQ.md
```

---

## 🔍 Troubleshooting

### Service does not start

```bash
docker compose logs live-mem-service --tail 50
docker compose logs waf --tail 20
```

### 401 Unauthorized

- Check your token: `Authorization: Bearer YOUR_TOKEN`
- Bootstrap key is not a token — create a token first via `admin_create_token`

### Consolidation fails

- Check LLMaaS credentials in `.env`
- Default timeout is 600s — increase `CONSOLIDATION_TIMEOUT` if needed
- Only one `bank_consolidate` at a time per space (asyncio lock)

---

## 🔗 Related Projects

| Project           | Description                                | Link                                                                         |
| ---------------- | ------------------------------------------ | ---------------------------------------------------------------------------- |
| **graph-memory** | Long-term memory (Knowledge Graph + RAG)   | [github.com/chrlesur/graph-memory](https://github.com/chrlesur/graph-memory) |

---

## 📄 License

Apache License 2.0

---

## 👤 Author

**Cloud Temple** — [cloud-temple.com](https://www.cloud-temple.com)

Developed by **Christophe Lesur**, CEO.

---

*Live Memory v0.6.0 — Shared working memory for collaborative AI agents*
