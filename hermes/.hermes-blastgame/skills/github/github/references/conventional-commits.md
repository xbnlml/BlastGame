# Conventional Commits

Format: `type(scope): description`

## Types

| Type | When | Example |
|------|------|---------|
| `feat` | New feature | `feat(auth): add OAuth2 login flow` |
| `fix` | Bug fix | `fix(api): handle null response` |
| `refactor` | Restructure, no behavior change | `refactor(db): extract query builder` |
| `docs` | Documentation | `docs: update API examples` |
| `test` | Tests | `test(auth): add token refresh tests` |
| `ci` | CI/CD config | `ci: add Python 3.12 to matrix` |
| `chore` | Maintenance, deps | `chore: upgrade pytest to 8.x` |
| `perf` | Performance | `perf(search): index users.email` |
| `style` | Formatting | `style: run black on src/` |
| `build` | Build system | `build: switch to hatch` |

Breaking changes: `feat(api)!: change auth to bearer tokens` or add `BREAKING CHANGE:` in footer.

Multi-line body (wrap at 72 chars):
```
feat(auth): add JWT authentication

- Add login/register endpoints
- Add middleware for protected routes

Closes #42
```
