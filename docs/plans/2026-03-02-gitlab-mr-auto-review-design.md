# GitLab MR Auto Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone service that auto-reviews GitLab MRs assigned to one reviewer and pushes a Markdown report to sohu agent and Feishu.

**Architecture:** A polling CLI loads assigned MRs from GitLab, runs AI review on each new MR SHA, writes markdown reports, pushes to external channels, then persists processed state in JSON. Integrations are isolated behind client classes for easier replacement.

**Tech Stack:** Python 3.10+, python-gitlab, requests, OpenAI SDK, pytest.

---

### Task 1: Data model and report rendering

**Files:**
- Create: `src/mr_auto_reviewer/models.py`
- Create: `src/mr_auto_reviewer/reporting.py`
- Test: `tests/test_reporting.py`

**Step 1: Write failing report test**

Create assertions for markdown title, MR purpose section, verdict, risk, findings, and suggestions.

**Step 2: Verify failure**

Run: `PYTHONPATH=src pytest -q`
Expected: import or assertion failure.

**Step 3: Implement report builder**

Add data classes and markdown generator.

**Step 4: Verify pass**

Run: `PYTHONPATH=src pytest tests/test_reporting.py -q`
Expected: PASS.

### Task 2: Pipeline orchestration

**Files:**
- Create: `src/mr_auto_reviewer/pipeline.py`
- Create: `src/mr_auto_reviewer/state_store.py`
- Test: `tests/test_pipeline.py`

**Step 1: Write failing pipeline test**

Create stubs for GitLab/reviewer/sohu/Feishu and assert only unprocessed MR is handled.

**Step 2: Verify failure**

Run: `PYTHONPATH=src pytest tests/test_pipeline.py -q`
Expected: FAIL before implementation.

**Step 3: Implement minimal pipeline**

Add `run_once`, report writing, push hooks, and state persistence.

**Step 4: Verify pass**

Run: `PYTHONPATH=src pytest tests/test_pipeline.py -q`
Expected: PASS.

### Task 3: External adapters and CLI

**Files:**
- Create: `src/mr_auto_reviewer/config.py`
- Create: `src/mr_auto_reviewer/gitlab_client.py`
- Create: `src/mr_auto_reviewer/ai_reviewer.py`
- Create: `src/mr_auto_reviewer/sohu_client.py`
- Create: `src/mr_auto_reviewer/feishu_client.py`
- Create: `src/mr_auto_reviewer/main.py`
- Create: `.env.example`
- Create: `README.md`

**Step 1: Add environment-based config**

Load GitLab, OpenAI, sohu, and Feishu values from `.env`.

**Step 2: Build each adapter**

Implement methods with explicit request payloads and response validation.

**Step 3: Wire CLI**

Support `run-once` and `watch` commands.

**Step 4: Verify import and tests**

Run: `PYTHONPATH=src pytest -q`
Expected: PASS.
