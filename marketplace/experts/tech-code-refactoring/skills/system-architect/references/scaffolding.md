# Project Scaffolding

Standard directory layouts for new projects. Prefer minimalism; add only what the project needs.

## Python (package or app)

```
project/
├── src/
│   └── <package_name>/
│       ├── __init__.py
│       └── ...
├── tests/
│   ├── __init__.py
│   └── test_*.py
├── docs/
├── pyproject.toml
├── README.md
├── .editorconfig
├── .gitignore
└── .env.example
```

- Use `src/` layout so the package is not imported from the repo root; install with `pip install -e .`.
- Alternative: flat `app/` or `<package_name>/` at root for small scripts or single-module apps.
- Config: `pyproject.toml` for tooling (Black, Ruff, mypy, pytest). Optional `.pylintrc` if using Pylint.

## JavaScript / TypeScript (Node or SPA)

```
project/
├── src/
│   ├── index.ts (or main entry)
│   └── ...
├── public/          (if SPA)
├── tests/           (or __tests__/, spec/)
├── package.json
├── tsconfig.json
├── .eslintrc.json
├── .editorconfig
├── README.md
├── .gitignore
└── .env.example
```

- Use `src/` for application code; config at repo root.
- Tests: `tests/` or colocated `__tests__/` / `*.spec.ts` depending on framework.
- Add `vite.config.ts`, `next.config.js`, etc. at root as needed.

## Full-stack (monorepo or separate repos)

- **Option A**: Two repos (frontend, backend); each follows the layout above.
- **Option B**: Monorepo with `apps/frontend/`, `apps/backend/`, shared code in `packages/` (e.g. pnpm workspaces, Turborepo, Nx).
- Prefer separate repos unless you need shared types or coordinated releases.

## Config files to add from templates

- `.editorconfig` – shared indent, charset, line endings.
- `.pylintrc` or Ruff in `pyproject.toml` – Python lint.
- `.eslintrc.json` + Prettier – JS/TS lint and format.
- `ARCHITECTURE.md` – overview, components, data flow, deployment, decisions.
