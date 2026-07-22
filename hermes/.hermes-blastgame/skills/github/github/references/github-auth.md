# GitHub Authentication Setup

Two paths: **git-only** (always available) or **gh CLI** (richer API access).

## Detection Flow
1. `gh auth status` → authenticated → use `gh` for everything
2. `gh` installed but not authenticated → use gh auth method
3. No `gh` → use git-only method

## Method 1: Git-Only (HTTPS with PAT)
1. Create token at https://github.com/settings/tokens (scopes: `repo`, `workflow`, `read:org`)
2. Store: `git config --global credential.helper store`
3. Test: `git ls-remote https://github.com/<user>/<repo>.git`
   Enter username + token as password

**Alternative — embed in remote URL:**
`git remote set-url origin https://<user>:<token>@github.com/<owner>/<repo>.git`

## Method 1b: Git-Only (SSH Keys)
```bash
ssh-keygen -t ed25519 -C "email@example.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
# Add to: https://github.com/settings/keys
ssh -T git@github.com
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

## Method 2: gh CLI
```bash
gh auth login          # Interactive browser login
echo "<token>" | gh auth login --with-token  # Token-based
gh auth setup-git      # Configure git credentials through gh
```

## API Access Without gh
```bash
export GITHUB_TOKEN="<token>"
# Then use: curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/...
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `git push` asks for password | Use personal access token as password |
| `Permission to X denied` | Token lacks `repo` scope |
| `Authentication failed` | Run `git credential reject` then re-auth |
| SSH connection refused | Add `Host github.com` with `Port 443` to `~/.ssh/config` |
| `gh: command not found` | Use git-only Method 1 |
