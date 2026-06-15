# Project Knowledge Base

**Stack:** Python 3.x | Repomix (Bun) | Playwright | Tkinter  
**Purpose:** Convert code repositories into LLM-optimized digest files (local dirs, Git remotes, websites)

## Structure

```
repo-to-md/
├── main.py              # Tkinter GUI (506 lines, Rose Pine theme)
├── repo_to_md.py        # CLI entry point (argparse)
├── logic/               # Core processing engine (see logic/AGENTS.md)
├── docs/                # Usage guides
└── .agents/skills/      # AI-assisted development skills
```

## Where to Look

| Task | Location | Notes |
|------|----------|-------|
| GUI logic, Tkinter widgets | `main.py` | 500+ line file with all UI setup |
| CLI args, entry dispatch | `repo_to_md.py` | Auto-detects input type (local/Git/web) |
| Batching, retry, planning | `logic/processor.py` | Core orchestration — 652 lines |
| Local files via Repomix | `logic/local.py` | Wraps `bun x repomix` for dirs |
| Remote Git via Repomix | `logic/git.py` | Wraps `--remote` flag |
| Web crawling | `logic/web.py` | Playwright + trafilatura |
| Constants, templates | `logic/config.py` | Limits, ignores, NotebookLM template |
| Tests | `test_processor.py` | Mock-based retry + batching tests |

## Conventions

- No `__init__.py` in `logic/` — modules loaded directly by name
- Repomix CLI via `bun x repomix` (not pip-installed)
- Python stdlib only for core logic; Playwright + trafilatura for web
- Output lands in `md-created/<name>_<timestamp>/`
- NotebookLM mode forces `.txt` extension (NotebookLM rejects `.xml`)
- Odoo addon detection via `__manifest__.py` for grouped batching

## Anti-Patterns

- **No `__init__.py` files** — modules are flat-loaded; don't add package inits
- **No direct file packing** — always delegate to Repomix CLI
- **No git clone** — remote repos handled via Repomix `--remote` flag
- **No deleting existing AGENTS.md content** — project-level directives preserved

## Commands

```bash
python repo_to_md.py /path/to/repo           # CLI: local dir
python repo_to_md.py https://github.com/...   # CLI: remote Git
python repo_to_md.py https://example.com       # CLI: web crawl
python main.py                                 # GUI
python -m pytest test_processor.py -v          # Run tests
```

## Notes

- The project has a CodeGraph index (`.codegraph/`) — 11 Python files, 179 symbols
- Not a git repo — no version history
- Default extensions favor Odoo projects: py, xml, js, csv, sh, sql, md, rst

---

# Agent Skills Index

This document tracks specialized skills and rules for AI agents working on this project.

---

## ⚠️ MANDATORY DIRECTIVE: CodeGraph for ALL Local Code Queries

**Any agent operating on this codebase MUST use CodeGraph (`codegraph_*` tools) as the PRIMARY mechanism for all local codebase queries.** This is not optional guidance — it is a hard requirement.

### What this means

| Instead of this (FORBIDDEN) | Do this (REQUIRED) |
|---|---|
| `grep` / `rg` / `Read` to find where a symbol is defined | `codegraph_search(query="SymbolName")` |
| `grep` to find what calls a function | `codegraph_callers(symbol="functionName")` |
| `grep` to find what a function calls | `codegraph_callees(symbol="functionName")` |
| `Read` loop across multiple files to understand a flow | `codegraph_trace(from="startSymbol", to="endSymbol")` |
| Reading files one-by-one to assess impact of a change | `codegraph_impact(symbol="targetSymbol")` |
| Multiple `Read` calls for several related symbols | `codegraph_explore(query="symbol1 symbol2 symbol3")` |
| `glob` + `Read` to understand project structure | `codegraph_files(path="src/")` |

### Exceptions (narrow and explicit)

The only situations where you may bypass CodeGraph:

1. **Literal text search** — finding a string literal, comment content, log message, or error text that is not a symbol name. Use `grep` for this.
2. **File editing** — you must `Read` a file before `edit`/`write` to it (the tool requires it). But you should already understand the symbol structure from CodeGraph before you read.
3. **CodeGraph index is stale** — the response includes "⚠️ Some files referenced below were edited since the last index sync…". In that case, `Read` only the specific files listed as stale.
4. **`.codegraph/` does not exist** — initialize it first or ask the user.

### Violation

Using `grep`, `Read`, `glob`, or spawning exploration agents for queries that CodeGraph can answer is a **violation of project protocol**. It wastes context tokens, is slower, and produces less accurate results.

---

## CodeGraph — Semantic Code Knowledge Graph

This project has a [CodeGraph](https://github.com/colbymchenry/codegraph) MCP server configured (`codegraph_*` tools). CodeGraph is a tree-sitter-parsed knowledge graph of every symbol, edge, and file. Reads are sub-millisecond and return structural information grep cannot.

### When to prefer CodeGraph over native search

Use CodeGraph for **structural** questions — what calls what, what would break, where is X defined, what is X's signature. Use native grep/Read only for **literal text** queries (string contents, comments, log messages) or after you already have a specific file open.

| Question | Tool |
|---|---|
| "Where is X defined?" / "Find symbol named X" | `codegraph_search` |
| "What calls function Y?" | `codegraph_callers` |
| "What does Y call?" | `codegraph_callees` |
| "How does X reach/become Y? / trace the flow from X to Y" | `codegraph_trace` (one call = the whole path, incl. callback/React/JSX dynamic hops) |
| "What would break if I changed Z?" | `codegraph_impact` |
| "Show me Y's signature / source / docstring" | `codegraph_node` |
| "Give me focused context for a task/area" | `codegraph_context` |
| "See several related symbols' source at once" | `codegraph_explore` |
| "What files exist under path/" | `codegraph_files` |
| "Is the index healthy?" | `codegraph_status` |

### Rules of thumb

- **Answer directly — don't delegate exploration.** For "how does X work" / architecture questions, answer with 2-3 `codegraph` calls: `codegraph_context` first, then ONE `codegraph_explore` for the source of the symbols it surfaces. For a specific **flow** ("how does X reach Y") start with `codegraph_trace` from→to — one call returns the whole path with dynamic hops bridged — then ONE `codegraph_explore` for the bodies; don't rebuild the path with `codegraph_search` + `codegraph_callers`. CodeGraph IS the pre-built index, so spawning a separate file-reading sub-task/agent — or running a grep + read loop — repeats work CodeGraph already did and costs more for the same answer.
- **Trust CodeGraph results.** They come from a full AST parse. Do NOT re-verify them with grep — that's slower, less accurate, and wastes context.
- **Don't grep first** when looking up a symbol by name. `codegraph_search` is faster and returns kind + location + signature in one call.
- **Don't chain `codegraph_search` + `codegraph_node`** when you just want context — `codegraph_context` is one call.
- **Don't loop `codegraph_node` over many symbols** — one `codegraph_explore` call returns several symbols' source grouped in a single capped call, while each separate node/Read call re-reads the whole context and costs far more.
- **Index lag — check the staleness banner, don't guess a wait.** When a `codegraph` response starts with "⚠️ Some files referenced below were edited since the last index sync…", the listed files are pending re-index — Read those specific files for accurate content. Files NOT in that banner are fresh and CodeGraph is authoritative for them. `codegraph_status` also lists pending files under "Pending sync".

### If `.codegraph/` doesn't exist

The MCP server returns "not initialized." Ask the user: *"I notice this project doesn't have CodeGraph initialized. Want me to run `codegraph init -i` to build the index?"*

---

## How to Use
1. Check the trigger column to find skills that match your current task.
2. Load the skill by reading the SKILL.md file at the listed path.
3. Follow ALL patterns and rules from the loaded skill.

## Skills
| Skill | Trigger | Path |
|-------|---------|------|
| (Sample) | when doing X | path/to/SKILL.md |
