# GitHub REST API Cheatsheet

Base: `https://api.github.com` | All requests: `-H "Authorization: token $GITHUB_TOKEN"`

Source the env helper: `source "${HERMES_HOME:-$HOME/.hermes}/skills/github/scripts/gh-env.sh"`

## Repositories
| Action | Method | Endpoint |
|--------|--------|----------|
| Get repo info | GET | `/repos/{owner}/{repo}` |
| Create (user) | POST | `/user/repos` |
| Create (org) | POST | `/orgs/{org}/repos` |
| Update | PATCH | `/repos/{owner}/{repo}` |
| Fork | POST | `/repos/{owner}/{repo}/forks` |
| Topics | PUT | `/repos/{owner}/{repo}/topics` |

## PRs
| Action | Method | Endpoint |
|--------|--------|----------|
| List | GET | `/repos/{o}/{r}/pulls?state=open` |
| Create | POST | `/repos/{o}/{r}/pulls` |
| List files | GET | `/repos/{o}/{r}/pulls/{n}/files` |
| Merge | PUT | `/repos/{o}/{r}/pulls/{n}/merge` |
| Review | POST | `/repos/{o}/{r}/pulls/{n}/reviews` |
| Inline comment | POST | `/repos/{o}/{r}/pulls/{n}/comments` |

## Issues
| Action | Method | Endpoint |
|--------|--------|----------|
| Create | POST | `/repos/{o}/{r}/issues` |
| Comment | POST | `/repos/{o}/{r}/issues/{n}/comments` |
| Add labels | POST | `/repos/{o}/{r}/issues/{n}/labels` |
| Add assignees | POST | `/repos/{o}/{r}/issues/{n}/assignees` |
| Search | GET | `/search/issues?q={q}+repo:{o}/{r}` |

## CI / Actions
| Action | Method | Endpoint |
|--------|--------|----------|
| List workflows | GET | `/repos/{o}/{r}/actions/workflows` |
| List runs | GET | `/repos/{o}/{r}/actions/runs` |
| Download logs | GET | `/repos/{o}/{r}/actions/runs/{id}/logs` |
| Re-run | POST | `/repos/{o}/{r}/actions/runs/{id}/rerun` |
| Trigger dispatch | POST | `/repos/{o}/{r}/actions/workflows/{id}/dispatches` |
| Commit status | GET | `/repos/{o}/{r}/commits/{sha}/status` |

## Releases & Secrets
| Action | Method | Endpoint |
|--------|--------|----------|
| Create release | POST | `/repos/{o}/{r}/releases` |
| Upload asset | POST | `https://uploads.github.com/.../releases/{id}/assets?name={n}` |
| List secrets | GET | `/repos/{o}/{r}/actions/secrets` |
| Set secret | PUT | `/repos/{o}/{r}/actions/secrets/{name}` |
| Get public key | GET | `/repos/{o}/{r}/actions/secrets/public-key` |

## Branch Protection
| Action | Method | Endpoint |
|--------|--------|----------|
| Get | GET | `/repos/{o}/{r}/branches/{b}/protection` |
| Set | PUT | `/repos/{o}/{r}/branches/{b}/protection` |
| Delete | DELETE | `/repos/{o}/{r}/branches/{b}/protection` |

## Rate Limits
Authenticated: 5,000 req/hr. Check: `curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit`

Pagination: `?per_page=100&page=N` — check `Link` header for `rel="next"`.
