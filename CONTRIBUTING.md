# ⛵ Contributing to ProjectCompass

Welcome aboard, sailor! We're glad you want to help steer this vessel.

## The Golden Rule: Issue First, Code Second

**Every contribution — feature or bugfix — must start with an open Issue.**

No pull request will be reviewed unless it references an existing, approved Issue. This keeps the crew aligned and avoids wasted effort sailing in the wrong direction.

### Reporting a Bug 🐙

1. Open an Issue with the **Bug** label.
2. Describe what happened, what you expected, and how to reproduce it.
3. Include browser, OS, and Docker/Python versions if relevant.
4. Wait for a maintainer to confirm and label it before submitting a fix.

### Proposing a Feature ⛵

1. Open an Issue with the **Feature** label.
2. Explain the use case: what problem does it solve and for whom?
3. A maintainer will discuss scope, design, and whether it fits the project's heading.
4. Only after approval should you hoist the sails and start coding.

## Workflow

```
1. Fork the repo
2. Create a branch from main:  git checkout -b feat/your-feature
3. Write your code — keep it minimal, no ballast
4. Run the linter:              uv run ruff check .
5. Push and open a PR referencing the Issue:  Closes #42
```

## Code Style — Trim the Sheets

- **Minimal code.** No verbose implementations, no dead weight. Every line should earn its place on deck.
- **No unnecessary comments.** The code should be self-explanatory. Comment only when the "why" isn't obvious.
- **Match the existing style.** Read the surrounding code before writing yours.
- **Use `uv`** for all Python operations — never `pip install` directly.
- **No tests unless asked.** When requested, use `pytest` and run with `uv run pytest`.

## Pull Request Checklist

- [ ] References an approved Issue (`Closes #N`)
- [ ] Branch is up to date with `main`
- [ ] `uv run ruff check .` passes with no new errors
- [ ] Commit messages are concise and descriptive
- [ ] No unrelated changes bundled in

## What We Won't Merge

- PRs without a linked Issue
- Dependency bumps from automated bots (we manage these internally)
- Changes that break existing functionality without discussion
- Code that adds unnecessary complexity or dependencies

## Ship's Log — Commit Messages

Keep them short and clear:

```
feat: add CSV export to query runner
fix: prevent crash on empty analysis metadata
docs: update k0s setup guide for v1.31
chore: bump scomp-link to 2.3.0
```

## Questions?

Open an Issue tagged **Question** — we'll get back to you. Fair winds! 🌊
