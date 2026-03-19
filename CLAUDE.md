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