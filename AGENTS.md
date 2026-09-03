This file provides guidance for AI agents and human contributors working on this Python (FastAPI + Uvicorn) project.

**All essential project information is stored in separate reference documents** - keep them up to date when making changes.

## Reference Documents

| Topic | Document |
|-------|----------|
| **Project overview** | [README.md](./README.md) |
| **Development setup** | [docs/setup.md](./docs/setup.md) |
| **Architecture & design** | [docs/architecture.md](./docs/architecture.md) |
| **Coding conventions** | [docs/coding-standards.md](./docs/coding-standards.md) |
| **Testing strategy** | [docs/testing.md](./docs/testing.md) |
| **Benchmarks** | [docs/benchmark-results.md](./docs/benchmark-results.md) |
| **Memory footprint** | [docs/memory-benchmarks.md](./docs/memory-benchmarks.md) |
| **Deployment & operations** | [docs/deployment.md](./docs/deployment.md) |

## Agent Instructions

- When adding, modifying, or removing features, **update the relevant reference document(s)**.
- After completing any change (code or docs), review all reference documents and update them if anything is now stale, inaccurate, or missing.
- If a required document does not exist, create it in the `docs/` folder and add a link to this table.
- For code changes, always check [coding-standards.md](./docs/coding-standards.md) and [testing.md](./docs/testing.md) before committing.
- Before proposing a new major change, review [architecture.md](./docs/architecture.md) to understand the current design.
- Use the [README.md](./README.md) as the entry point for new contributors - keep it concise and up to date.
- All documents are written in Markdown and should be accessible via relative paths (as linked above).

## Project Context (quick summary)

- **Language**: Python (≥ 3.12 per `pyproject.toml`).
- **Runtime deps**: `fastapi`, `uvicorn[standard]`, `python-multipart` (managed with `uv`; see [docs/setup.md](./docs/setup.md)).
- **Entry point**: `web-file-manager` console script / `python -m web_file_manager` → `main()` in `__init__.py`.
- **Maintainers**: See [README.md](./README.md) for contacts.

Remember: **this file is a navigation hub, not a knowledge base**. Detailed information belongs in the linked documents. Always keep them synchronized with the codebase.
