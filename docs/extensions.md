# Server extensions

A product built on Octop can ship as its own Python package that depends on the
`octop` wheel, instead of a fork that patches Octop's files. The package
declares one entry point in the `octop.extensions` group:

```toml
[project.entry-points."octop.extensions"]
my_product = "my_product.extension:extension"
```

The entry point resolves to any object. Octop calls each of the hooks below
only if the object defines it.

| Hook | When | Use it to |
|------|------|-----------|
| `async on_startup(server)` | End of runtime boot (database, agents, gateway, cron are up) | Start background tasks, warm caches |
| `async on_shutdown(server)` | First step of `OctopServer.stop`, database still open | Stop background tasks |
| `configure_app(app, server)` | In `build_app`, before the dashboard catch-all route | `app.include_router(...)`, exception handlers, static mounts |
| `public_paths() -> PublicPaths` | First request | Name `/api/...` paths that skip the Octop JWT (`exact`, `prefixes`) and that stay reachable before setup creates the first user (`setup_exact`, `setup_prefixes`) |

### Registry contributions

These hooks return plain data. Octop reads each one once per process and
caches the result. An extension can only add entries: a key or id Octop
already ships wins, and the extension's copy is logged and ignored.

| Hook | Returns | Effect |
|------|---------|--------|
| `i18n_bundles()` | `{"en": {...}, "zh": {...}}` nested string tables | Merged under the built-in bundles, so `tr("my_product.title", locale)` works and `tools.<name>` labels show up in the tool pickers |
| `provider_presets()` | Iterable of preset dicts, same shape as the bundled ones (`id` required) | Listed before the bundled presets in the model provider picker |
| `hitl_excluded_tools()` | Iterable of tool names | Hidden from the approval picker; those tools always run without HITL |
| `sidebar_nav_keys()` | Iterable of keys | Accepted in a user's saved sidebar layout. The dashboard only renders keys it knows, so the product's own UI draws them |
| `virtual_channels()` | Iterable of thread channel types | Treated like `dashboard` / `cli` / `mcp`: in-process, never an IM outbound target |

Do not call `tr()` while the extension module is being imported; the bundles
are merged on first lookup, after every extension has loaded.

```python
# my_product/extension.py
from fastapi import APIRouter
from octop.infra.extensions import PublicPaths

router = APIRouter(prefix="/api/my-product")


class Extension:
    async def on_startup(self, server): ...
    async def on_shutdown(self, server): ...

    def configure_app(self, app, server):
        app.include_router(router)

    def public_paths(self):
        return PublicPaths(exact=("/api/my-product/status",))


extension = Extension()
```

Rules:

- Extensions load once per process, sorted by entry point name. An extension
  that fails to import is logged and skipped.
- An exception in `on_startup` stops the server from starting. The extensions
  that already started get `on_shutdown` in reverse order, then the runtime
  is stopped and the database closed, so a failed first-run database bind can
  be retried. `on_shutdown` runs only for extensions whose startup finished
  (an extension without `on_startup` counts as started).
- A failing `on_shutdown` is logged, and the other extensions still shut down.
- Public paths must start with `/api/`. A route listed there must
  authenticate the caller itself.
- Agent tools, skills, middleware hooks, and IM channels belong in harness
  plugins (see [plugin-package.md](plugin-package.md)), not here.
