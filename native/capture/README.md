# Native capture (macOS)

A standalone macOS 13+ component for multi-page document scanning and photo capture with iPhone Continuity Camera, photo selection from a USB-connected iPhone, and local PDF/image import. It has no Octop server, Agent, model, or business-plugin dependency. [中文说明](README_CN.md).

Build on a Mac with Xcode Command Line Tools, then invoke the Python 3 CLI from the repository root:

```sh
sh native/capture/build.sh
./native/capture/octop-capture scan --output ./work/captures
```

Modes: `scan`, `photo`, `album`, `import`. `album` requires USB, an unlocked iPhone and trust for the Mac; it accesses device-exposed media, not album groups or iCloud-only originals. All capture modes require a logged-in macOS graphical session. Builds target macOS 13+ for the current machine architecture; generated, ad hoc signed `.app` files are ignored by Git.

The CLI creates a unique session directory and writes JSON to stdout and `capture.json`. Version 1 contains `schema_version`, `session_id`, `mode`, `status`, `files` and `reason`; created sessions include `directory` and `manifest_path`. Each file has an absolute `path`, `filename`, `media_type`, `size` and optional `preview_path`. Scans preserve the multi-page PDF and generate a first-page PNG preview. Original imports are preserved; previews are separate files. HEIC/TIFF/BMP previews are resized to a maximum logical dimension of 800 points.

Check `status`, not just the process exit code: `ok` and user `cancelled` return exit code 0; `timeout`, `unavailable` and `error` return 1; invalid CLI arguments return 2. The default timeout is 600 seconds (`--timeout` overrides it). The native helper's `result.json` is an internal protocol. Error results are also persisted when the session directory is writable. On failure, intermediate files may remain in the session directory; callers own their retention policy.

Skills and other applications can call the CLI, read `files[].path` on success, and implement their own OCR, preview, upload, or filing workflow. Copy the CLI and `.app` together when using the component in another project. Octop’s chat composer uses a small optional server adapter to save captured files through the existing inbound attachment store; the standalone CLI stays independent.

Hardware-independent checks:

```sh
sh native/capture/test_scan.sh
uv run --frozen pytest tests/unit/test_native_capture_component.py
```

Manual testing still requires a real iPhone: scan multiple pages, take a photo, select multiple USB photos, import existing files, cancel, and verify timeout handling. Check originals, previews, independent session directories, and matching stdout/manifest results.

## Octop chat composer

Build the helper, restart the Octop server and refresh the dashboard. The attachment button offers local file upload, iPhone scanning, photo capture and USB photo selection on macOS when the helper is present. Captures become pending attachments; the user sends them through the existing message pipeline. Original PDFs retain separate first-page previews. No plugin installation or Agent manager changes are required.

The server defaults to this repository’s built helper. For an installed Python package, set `OCTOP_NATIVE_CAPTURE_HELPER` to the absolute path of `OctopCapture.app/Contents/MacOS/OctopCapture` before starting the server. The server needs a logged-in macOS graphical session. Captures are owner/admin only, serialized per server process and limited by the existing upload size setting. Non-macOS servers keep the original file upload button. A reverse proxy must allow capture requests up to ten minutes.
