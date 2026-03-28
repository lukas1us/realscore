## README Maintenance

After **every** operation that modifies the directory structure — including creating,
deleting, renaming, or moving any file or folder — update the `## Architecture` section
in `README.md` with the current directory tree.

### Rules
- Preserve the exact format of the existing tree (backtick fenced block inside `## Architecture`)
- Keep all inline comments (e.g. `# FastAPI app entry point`) — update or add them for new files
- Exclude: `__pycache__`, `.venv`, `.env`, `*.pyc`, `.git`
- Update the tree **before** confirming the task as done
- Never skip this step, even for "small" changes

## Tests

After **every** code change, run the test suite and act on the results:
```bash
pytest tests/test_scoring.py tests/test_regions.py tests/test_benchmarks.py -v
```

### Rules
- If all tests pass → proceed and confirm the task as done
- If any test fails → fix the failure before marking the task complete; do not ask for permission to fix it
- If a test failure is caused by an intentional breaking change → update the affected tests to match
  the new behavior, then re-run to confirm green
- Never mark a task as done while tests are red


# Git workflow

### Branch naming
```
feature/short-description     # new features
fix/short-description         # bug fixes
refactor/short-description    # refactoring without behavior change
chore/short-description       # deps, config, tooling
```

### Commit after every completed task
After tests pass and README is reviewed, always commit:
```bash
git add -A
git commit -m "<type>: <short description>"
```

Commit message types:
- feat: new feature
- fix: bug fix
- refactor: code change without behavior change
- test: adding or updating tests
- chore: dependencies, config, tooling
- docs: documentation only

Examples:
```
feat: add CSV import for Air Bank
fix: correct account balance recalculation on transaction delete
test: add API tests for investments/purchases
docs: update README with ECB API setup
```

### Never commit
- Failing tests
- .env files (check .gitignore)
- node_modules
- Build artifacts

---

## Full Market Scan — CLI flags

`backend/jobs/full_market_scan.py` accepts two rate-limiting flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--request-delay SECONDS` | `0.5` | Minimum seconds between API requests per worker thread (ID collection and detail scraping). |
| `--max-retries N` | `3` | How many times to retry a failed detail scrape before skipping the record. On HTTP 429 or connection error the worker waits `2^attempt` seconds (exponential backoff). On HTTP 403/404 it skips immediately without retrying. |

Example:
```bash
python -m backend.jobs.full_market_scan --request-delay 1.0 --max-retries 5
```

---
