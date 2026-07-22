---
name: github
description: "Full GitHub workflow: auth, PRs, code review, issues, repo management, codebase inspection."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, Auth, Pull-Requests, Code-Review, Issues, CI/CD, Repositories, Releases, Git]
---

# GitHub — Unified Workflow

Six aspects of GitHub work in one skill with a shared auth section, eliminating duplicated setup code.

## Shared — Auth Detection & Setup

All GitHub operations share this auth detection. Source from the shared script, or inline:

**Via shared script (recommended):**
```bash
source "${HERMES_HOME:-$HOME/.hermes}/skills/github/scripts/gh-env.sh"
```

**Inline detection (when script is unavailable):**
```bash
if command -v gh &>/dev/null && gh auth status &>/dev/null; then
  AUTH="gh"
else
  AUTH="curl"
  if [ -z "$GITHUB_TOKEN" ]; then
    if _hermes_env="${HERMES_HOME:-$HOME/.hermes}/.env"; [ -f "$_hermes_env" ] && grep -q "^GITHUB_TOKEN=" "$_hermes_env"; then
      GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" "$_hermes_env" | head -1 | cut -d= -f2 | tr -d '\n\r')
    elif grep -q "github.com" ~/.git-credentials 2>/dev/null; then
      GITHUB_TOKEN=$(grep "github.com" ~/.git-credentials 2>/dev/null | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
    fi
  fi
fi

REMOTE_URL=$(git remote get-url origin)
OWNER_REPO=$(echo "$REMOTE_URL" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
OWNER=$(echo "$OWNER_REPO" | cut -d/ -f1)
REPO=$(echo "$OWNER_REPO" | cut -d/ -f2)
```

## 1. Authentication Setup

See `references/github-auth.md` for full setup covering:
- **HTTPS with PAT** — via `git config --global credential.helper store` + personal access token
- **SSH keys** — via `ssh-keygen` + adding to GitHub settings
- **gh CLI** — via `gh auth login` or token-based login
- **API-only (no gh)** — via `GITHUB_TOKEN` env var

Also ships `scripts/gh-env.sh` — source it to auto-detect auth method, GitHub user, and current repo owner/repo.

## 2. Repository Management

See `references/github-api-cheatsheet.md` for full REST API endpoint reference. Summary:

| Task | gh | git + curl |
|------|-----|-----------|
| Clone | `gh repo clone o/r` | `git clone https://github.com/o/r.git` |
| Create repo | `gh repo create name --public` | `curl POST /user/repos` |
| Fork | `gh repo fork o/r --clone` | `curl POST /repos/o/r/forks` + `git clone` |
| Edit settings | `gh repo edit --...` | `curl PATCH /repos/o/r` |
| Create release | `gh release create v1.0` | `curl POST /repos/o/r/releases` |
| Set secret | `gh secret set KEY` | `curl PUT /repos/o/r/actions/secrets/KEY` (+ encryption) |
| Branch protection | `gh api ...` | `curl PUT /repos/o/r/branches/main/protection` |
| List workflows | `gh workflow list` | `curl GET /repos/o/r/actions/workflows` |
| Rerun CI | `gh run rerun ID` | `curl POST /repos/o/r/actions/runs/ID/rerun` |
| Gists | `gh gist create` | `curl POST /gists` |

## 3. PR Workflow

Complete lifecycle: branch → commit → push → CI → merge.

### Branch & Commit (pure git)
```bash
git checkout -b feat/description
git add files
git commit -m "feat(scope): description"
git push -u origin HEAD
```

### Create PR
**With gh:** `gh pr create --title "..." --body "..." --label "enhancement"`
**With curl:** `curl -X POST https://api.github.com/repos/$OWNER/$REPO/pulls -d '{"title":"...","head":"$BRANCH","base":"main"}'`

### Monitor CI
**With gh:** `gh pr checks --watch`
**With curl:** Poll `GET /repos/$OWNER/$REPO/commits/$SHA/status` and `check-runs`

### Auto-Fix CI Loop
1. Check CI → identify failures
2. Read logs → understand error
3. Fix code → `git add . && git commit -m "fix: ..." && git push`
4. Re-check, repeat up to 3 attempts

### Merge
**With gh:** `gh pr merge --squash --delete-branch`
**With curl:** `curl -X PUT /repos/$OWNER/$REPO/pulls/$N/merge -d '{"merge_method":"squash"}'`

### Templates
- `templates/pr-body-bugfix.md` — structured PR body for bug fixes
- `templates/pr-body-feature.md` — structured PR body for features
- `references/conventional-commits.md` — commit message format reference
- `references/ci-troubleshooting.md` — common CI failure diagnosis

## 4. Code Review

Review local changes (pre-push) or open PRs.

### Local Review (pure git)
```bash
git diff main...HEAD --stat     # scope
git diff main...HEAD             # full diff
git diff main...HEAD -- file.py  # per-file
```

### PR Review
**Get context:** `gh pr view N && gh pr diff N --name-only`
**Checkout locally:** `git fetch origin pull/N/head:pr-N && git checkout pr-N`
**Post review:** `gh pr review N --approve --body "..."` or curl with inline comments

### Review Checklist
- Correctness, edge cases, error paths
- No hardcoded secrets, SQL injection, XSS
- Clear naming, DRY, single responsibility
- Tests for new code paths
- No N+1 queries, blocking ops in async code

### Template
- `references/review-output-template.md` — structured review comment format with severity icons

## 5. Issues Management

Create, search, triage, label, assign, and close issues.

### Viewing
`gh issue list --state open --label "bug"` or `curl GET /repos/$O/$R/issues`

### Creating
`gh issue create --title "..." --body "..." --label "bug" --assignee @me`
Or `curl POST /repos/$O/$R/issues` with JSON body.

### Templates
- `templates/bug-report.md` — structured bug report template
- `templates/feature-request.md` — structured feature request template

### Managing
| Action | gh | curl |
|--------|-----|------|
| Add label | `gh issue edit N --add-label "bug"` | `POST .../issues/N/labels` |
| Assign | `gh issue edit N --add-assignee user` | `POST .../issues/N/assignees` |
| Comment | `gh issue comment N --body "..."` | `POST .../issues/N/comments` |
| Close | `gh issue close N` | `PATCH .../issues/N -d '{"state":"closed"}'` |

## 6. Codebase Inspection

Use `pygount` for LOC counts and language breakdown:

```bash
pip install --break-system-packages pygount
pygount --format=summary --folders-to-skip=".git,node_modules,venv,.venv,__pycache__" .
```

Columns: Language, Files, Code lines, Comment lines, % of total. Adjust `--folders-to-skip` per project type. Filter by language with `--suffix=py`. JSON output via `--format=json`.

## Quick Reference Table

| Task | gh command | curl endpoint |
|------|-----------|---------------|
| List issues | `gh issue list` | `GET /repos/{o}/{r}/issues` |
| Create issue | `gh issue create ...` | `POST /repos/{o}/{r}/issues` |
| Add labels | `gh issue edit N --add-label ...` | `POST /repos/{o}/{r}/issues/N/labels` |
| Close issue | `gh issue close N` | `PATCH /repos/{o}/{r}/issues/N` |
| List PRs | `gh pr list` | `GET /repos/{o}/{r}/pulls` |
| Create PR | `gh pr create ...` | `POST /repos/{o}/{r}/pulls` |
| Review PR | `gh pr review N ...` | `POST /repos/{o}/{r}/pulls/N/reviews` |
| Merge PR | `gh pr merge --squash` | `PUT /repos/{o}/{r}/pulls/N/merge` |
| Check CI | `gh pr checks` | `GET /repos/{o}/{r}/commits/{sha}/status` |
| Rerun CI | `gh run rerun N` | `POST /repos/{o}/{r}/actions/runs/N/rerun` |
| Create release | `gh release create v1.0` | `POST /repos/{o}/{r}/releases` |
| List workflows | `gh workflow list` | `GET /repos/{o}/{r}/actions/workflows` |
| Set secret | `gh secret set KEY` | `PUT /repos/{o}/{r}/actions/secrets/KEY` |
| Edit repo | `gh repo edit --...` | `PATCH /repos/{o}/{r}` |
| Fork repo | `gh repo fork o/r` | `POST /repos/{o}/{r}/forks` |
| Search repos | `gh search repos ...` | `GET /search/repositories?q=...` |
