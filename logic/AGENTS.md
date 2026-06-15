# logic/ — Processing Engine

**Purpose:** Core processing orchestration — all input types (local, Git, web) flow through here.

## Structure

```
logic/
├── processor.py   # RepositoryProcessor: planning, batching, retry, binary handling
├── local.py       # LocalProcessor: wraps `bun x repomix <dir>`
├── git.py         # GitProcessor: wraps `bun x repomix --remote <url>`
├── web.py         # WebProcessor: Playwright crawl + trafilatura extraction
├── config.py      # Constants: limits, manifests, ignores, NotebookLM template
└── base.py        # BaseProcessor: log + progress callbacks base class
```

## Key Logic

| Concern | Module | Details |
|---------|--------|---------|
| Smart batching | `processor.py:_build_batches` | Groups files by Odoo addon root, priority, and size |
| Retry on overflow | `processor.py:_run_local_process_with_retry` | Parses Repomix "Part size > limit" error, grows split |
| Token budgeting | `processor.py:_apply_token_split_limit` | Converts max_tokens → MB (6 bytes/token heuristic) |
| Batch staging | `processor.py:_stage_batch_files` | Hard-links files into temp dirs per batch |
| Odoo addon detection | `processor.py:_find_odoo_addon_roots` | Scans for `__manifest__.py` to keep addons cohesive |
| Stats parsing | `local.py`, `git.py` | Regex extraction from Repomix stdout (identical logic) |

## Conventions

- No `__init__.py` here — modules are imported by name from `repo_to_md.py` and `main.py`
- Processors inherit from `BaseProcessor` (provides `log()` and `progress_callback`)
- `_count_total_words()` duplicated in `local.py` and `git.py` — known DRY gap
- All Repomix subprocess calls use `capture_output=True, text=True, check=True`

## Flow (Local Repo)

```
repo_to_md.py
  → RepositoryProcessor.process_repo()
    → plan_local_processing()       # walk files, score, group, batch
    → _orchestrate_binaries()       # copy images/audio referenced
    → _process_local_batches() OR _run_local_process_with_retry()
      → LocalProcessor.process()      # bun x repomix
      → _sanitize_output_files()      # wrap long lines
```

## Anti-Patterns

- **Never call Repomix directly** — always go through `LocalProcessor.process()` or `GitProcessor.process_remote()`
- **Never add `__init__.py`** — breaks the flat-import pattern
- **Never hardcode paths** — use `REPOMIX_CMD` from config
