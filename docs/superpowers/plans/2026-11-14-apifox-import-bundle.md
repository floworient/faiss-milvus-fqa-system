# Apifox Import Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a complete, versioned Apifox import bundle for every current API route, including schemas, environment variables, scripts, assertions, fixtures, and usage documentation.

**Architecture:** A deterministic Python generator derives OpenAPI from the FastAPI app and writes a Postman Collection v2.1 plus environment and fixtures. Repository tests run the generator in a temporary directory and validate route coverage, variable flow, scripts, JSON syntax, and secret/path safety.

**Tech Stack:** Python, FastAPI OpenAPI, Postman Collection v2.1 JSON, pytest

**Spec:** `docs/superpowers/specs/2026-11-14-apifox-import-bundle-design.md`

## Global Constraints

- Output lives under `docs/apifox/`.
- Cover all 11 current API operations.
- Use `{{base_url}}` in Collection requests and `http://127.0.0.1:8000` in the local environment.
- Include no credentials, absolute file paths, or fixed server-generated IDs.
- Treat SSE as a dedicated debug request; do not parse it as ordinary JSON.

## Review Focus

- FastAPI route additions must make bundle validation fail until regenerated.
- File upload bodies must remain portable and use only relative fixture paths.
- Async upload/delete task IDs must not overwrite one another.
- A failed response must not silently poison later environment variables.
- SSE assertions must not call `pm.response.json()`.

---

### Task 1: Bundle contract and deterministic generator

**Files:**
- Create: `tests/unit/test_apifox_bundle.py`
- Create: `scripts/generate_apifox_bundle.py`

**Interfaces:**
- Produces: `generate_bundle(output_dir: Path) -> None`.

- [ ] Write failing tests for all 11 operations, Postman v2.1 metadata, environment defaults, variable extraction, SSE safety, relative fixtures, and deterministic JSON generation.
- [ ] Run `python -m pytest tests/unit/test_apifox_bundle.py -q` and verify RED because the generator does not exist.
- [ ] Implement the generator and run the focused test to GREEN.

### Task 2: Generate, document, and verify the import package

**Files:**
- Create: `docs/apifox/openapi.json`
- Create: `docs/apifox/rag-knowledge-qa.postman_collection.json`
- Create: `docs/apifox/local.postman_environment.json`
- Create: `docs/apifox/fixtures/knowledge.md`
- Create: `docs/apifox/fixtures/evaluation.template.jsonl`
- Create: `docs/apifox/prepare_evaluation.py`
- Create: `docs/apifox/README.md`

**Interfaces:**
- Consumes: `generate_bundle(output_dir: Path) -> None` from Task 1.

- [ ] Run the generator against `docs/apifox`.
- [ ] Document Apifox import order, fixture selection, workflow order, polling rules, SSE checks, and regeneration command.
- [ ] Run focused and full backend tests, compile checks, JSON/JSONL parsing, frontend tests/typecheck/build, and `git diff --check` excluding the user-owned `.env`.
- [ ] Commit as `docs: add complete Apifox import bundle`.
