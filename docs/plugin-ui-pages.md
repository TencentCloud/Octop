# Standalone plugin pages

Plugins may expose a dashboard page without requiring a configured model,
expert or chat. An authenticated user opens **Settings → Plugin pages → Open**.
Installing and enabling plugins retain their existing permissions; page API
requests use the signed-in user's permissions.

Declare the usual UI entry in `plugin.yaml`:

```yaml
id: page-example
version: 0.1.0
name: Page example
kind: tool
entry: main.py
ui:
  entry: ui/index.js
  manifest: ui/manifest.json
```

`main.py` may have an empty `setup(ctx)` if the plugin has no agent tools. A page
does not require a tool result. Declare its page IDs and titles in the UI manifest:

```json
{
  "pages": [{ "id": "welcome", "title": "Welcome" }]
}
```

Ship a self-contained ESM entry, as with tool renderers:

```javascript
const React = window.__OCTOP_REACT__;

export function setup(host) {
  host.registerPage({
    id: "welcome",
    component: function Welcome({ pluginId, host }) {
      const { locale } = host.getPageContext();
      return React.createElement("p", null, `${pluginId}: ${locale}`);
    },
  });
}
```

Page IDs use 1–64 lowercase letters, digits, `_` or `-`, beginning with a letter
or digit. IDs must be unique within the manifest; titles must be non-empty and at
most 120 characters. A manifest may declare up to 20 pages. Registering an
undeclared ID fails, and the host supplies the owning plugin ID and title.

The page route is `/extensions/<plugin-id>/<page-id>`. Page props are
`{ pluginId, host }`. The page host exposes:

- `getPageContext()` → `{ locale, theme }`; no agent or conversation is required.
- `request(path, init?)` → authenticated JSON request under the instance's `/api`.
  It does not expose the raw token or bypass API permission checks.

Page and tool renderers may coexist in one UI entry. Tool renderers retain
`registerRenderer` and their existing tool-call host. Renderer-only manifests
remain supported. Page registrations are removed when plugin availability is
resynchronized after disabling, uninstalling or reloading a plugin. Refresh the
dashboard after changing plugins using the CLI.

This is a proposed public extension. Older hosts without `registerPage` can be
detected using `typeof host.registerPage === "function"`; their tool UIs continue
to work, but they do not provide the standalone page route.
