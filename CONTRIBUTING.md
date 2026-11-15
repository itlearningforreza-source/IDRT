# Contributing to IDRC Python

Thank you for your interest in contributing! This document provides guidelines
to ensure a smooth collaboration process.

---

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Workflow](#development-workflow)
4. [Coding Standards](#coding-standards)
5. [Test Requirements](#test-requirements)
6. [Pull Request Process](#pull-request-process)
7. [Commit Message Convention](#commit-message-convention)

---

## Code of Conduct

This project follows a standard Code of Conduct. We expect all contributors to:

- Be respectful and inclusive.
- Assume good faith in discussions.
- Prioritise the security and correctness of financial software above all else.

---

## Getting Started

### 1. Fork and clone

```bash
git clone https://github.com/<your-username>/idrc-python.git
cd idrc-python
```

### 2. Set up a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows
```

### 3. Install dev dependencies

```bash
pip install -e ".[dev]"
```

### 4. Verify everything passes

```bash
python -m pytest
```

Expected: **158 passed, 0 failed**.

---

## Development Workflow

```
main        ← stable, tagged releases only
  └── develop   ← integration branch
        └── feature/<name>   ← your branch
```

1. Branch off `develop`: `git checkout -b feature/my-feature develop`
2. Write code and tests.
3. Run the full test suite and linter before pushing.
4. Open a PR targeting `develop`.

---

## Coding Standards

### Style

- Code is formatted with **ruff** (`ruff format .`) — line width 100.
- Imports are sorted by ruff isort.
- All public functions, methods, and classes must have **docstrings**.
- Type hints are required on all function signatures (enforced by mypy strict).

### Run linting locally

```bash
ruff check .
ruff format --check .
mypy idrc/
```

All three must exit `0` before a PR is opened.

### Key principles (financial software)

| Principle | Why |
|-----------|-----|
| No floating-point arithmetic on amounts | Use raw integers (18 decimals) only |
| Checks-Effects-Interactions ordering | Prevents re-entrancy / state corruption |
| Raise explicit exceptions | Never silently fail or return `None` on errors |
| Every privileged function checks caller role | Mirrors Solidity `onlyRole` modifier |

---

## Test Requirements

- Every new feature must be accompanied by tests in `tests/`.
- Test file naming: `test_<module>.py`.
- Test class naming: `Test<FeatureName>`.
- The suite must remain at **100 % pass rate** — no skipped tests without justification.
- Aim to keep branch coverage ≥ 90 % (checked by `pytest --cov`).

```bash
# Full test run with coverage report
pytest --cov=idrc --cov-report=term-missing
```

---

## Pull Request Process

1. Fill in the PR template completely.
2. Link any relevant issue(s).
3. Ensure CI (GitHub Actions) is green before requesting review.
4. Request review from at least **one** maintainer.
5. Address all review comments before merging.
6. Squash-merge into `develop`; PRs from `develop` → `main` are done by maintainers at release time.

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `security`

**Examples:**

```
feat(token): add supply cap enforcement to mint()
fix(permit): handle clock drift in deadline validation
test(bridge): add replay-attack regression test
docs(readme): update quick-start example for v1.0
security(multisig): enforce timelock on all role-change proposals
```

---

Thank you for helping make IDRC safer and more robust! 🇮🇩
