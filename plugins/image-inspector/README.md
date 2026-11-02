# Image Inspector

An optional Octop tool plugin that invokes the current multimodal model to
review a workspace image and returns a textual visual-quality assessment.

Use it for layout defects that OCR cannot detect:

- clipped or overlapping text;
- misaligned or uneven cards;
- insufficient spacing;
- weak contrast or hierarchy;
- incorrect visual density.

## Install independently

```bash
octop plugin install ./plugins/image-inspector --force
```

Enable the plugin in Admin -> Plugins, then enable `inspect_image` for the
agent in Tool management.

## Agent workflow

1. Generate an image with `generate_image`.
2. Read the returned `localPath`.
3. Call `inspect_image` with that exact path when visual review is needed.
4. Use the returned text assessment before delivering or revising the image.

The tool is manual. It resolves images from `OCTOP_HOME`, `OCTOP_DATA_DIR`, and
the default `~/.octop` layout, including Docker-sandbox files materialized under
`.harness-materialize/`. It does not run automatically after generation and does
not modify the image. Each call sends the image as a data URL to a dedicated
model request, so it consumes model tokens in addition to the outer agent turn.
That request is isolated from the parent conversation stream; its review is
returned only as the tool result and is not sent to the user as a separate
message.

## Security

- Images must be under an Octop `agents/` or `workspaces/` directory.
- Supported formats: PNG, JPEG, WebP.
- Maximum size: 20 MiB.
- HTTP(S) URL fetching is not supported.
- The plugin does not modify Octop package files.
