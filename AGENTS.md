# Repository Guidelines

## Testing Before Commit

- Before every commit, run the local test suite. At minimum, run the tests that
  also run in GitHub CI:
  `uv run --project . reuse lint`,
  `uv run --project . -m pytest -q -k "not regression"`, and
  `uv run --project . -m pytest -q -k regression --basetemp=.pytest-tmp`.
- If a local-only untracked file makes a whole-repository check fail, verify the
  same check from a clean checkout.

## Commit Messages

- Match the style of nearby commits in this repository.
- Use a short, imperative subject line, optionally with a scope prefix:
  `docker: add missing TeX packages`.
- Keep the subject concise and do not end it with punctuation.
- Separate the subject from the body with a blank line.
- Hard-wrap commit message body lines at about 80 columns.
- Write detailed bodies.
- In the body, explain the motivation, the behavior change, and any relevant
  root cause.
- Include verification commands or test results when they are relevant.
- For multi-commit fixes, keep commits logically split. For example, first add
  or expose the regression, then fix the underlying issue.

Before finalizing rewritten commits, check wrapping with:

```sh
git log -2 --format=%B | awk '{ if (length($0) > 80) print length($0), $0 }'
```
