#!/usr/bin/env bash
# GitHub environment detection helper for Hermes Agent skills.
# Source this script to auto-detect auth method, user, and repo.
#
# Usage:
#   source "${HERMES_HOME:-$HOME/.hermes}/skills/github/scripts/gh-env.sh"
#
# Sets (all exported):
#   GH_AUTH_METHOD  - "gh", "curl", or "none"
#   GITHUB_TOKEN    - personal access token (set if method is "curl")
#   GH_USER         - GitHub username
#   GH_OWNER        - repo owner  (only if inside a git repo with a github remote)
#   GH_REPO         - repo name   (only if inside a git repo with a github remote)
#   GH_OWNER_REPO   - owner/repo  (only if inside a git repo with a github remote)

GH_AUTH_METHOD="none"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
GH_USER=""

if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
    GH_AUTH_METHOD="gh"
    GH_USER=$(gh api user --jq '.login' 2>/dev/null)
elif [ -n "$GITHUB_TOKEN" ]; then
    GH_AUTH_METHOD="curl"
elif _hermes_env="${HERMES_HOME:-$HOME/.hermes}/.env"; [ -f "$_hermes_env" ] && grep -q "^GITHUB_TOKEN=" "$_hermes_env" 2>/dev/null; then
    GITHUB_TOKEN=$(grep "^GITHUB_TOKEN=" "$_hermes_env" | head -1 | cut -d= -f2 | tr -d '\n\r')
    [ -n "$GITHUB_TOKEN" ] && GH_AUTH_METHOD="curl"
elif [ -f "$HOME/.git-credentials" ] && grep -q "github.com" "$HOME/.git-credentials" 2>/dev/null; then
    GITHUB_TOKEN=$(grep "github.com" "$HOME/.git-credentials" | head -1 | sed 's|https://[^:]*:\([^@]*\)@.*|\1|')
    [ -n "$GITHUB_TOKEN" ] && GH_AUTH_METHOD="curl"
fi

if [ "$GH_AUTH_METHOD" = "curl" ] && [ -z "$GH_USER" ]; then
    GH_USER=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
        https://api.github.com/user 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('login',''))" 2>/dev/null)
fi

GH_OWNER=""
GH_REPO=""
GH_OWNER_REPO=""

_remote_url=$(git remote get-url origin 2>/dev/null)
if [ -n "$_remote_url" ] && echo "$_remote_url" | grep -q "github.com"; then
    GH_OWNER_REPO=$(echo "$_remote_url" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
    GH_OWNER=$(echo "$GH_OWNER_REPO" | cut -d/ -f1)
    GH_REPO=$(echo "$GH_OWNER_REPO" | cut -d/ -f2)
fi
unset _remote_url

echo "GitHub Auth: $GH_AUTH_METHOD"
[ -n "$GH_USER" ]       && echo "User: $GH_USER"
[ -n "$GH_OWNER_REPO" ] && echo "Repo: $GH_OWNER_REPO"
[ "$GH_AUTH_METHOD" = "none" ] && echo "⚠ Not authenticated — see github skill § Authentication"

export GH_AUTH_METHOD GITHUB_TOKEN GH_USER GH_OWNER GH_REPO GH_OWNER_REPO
