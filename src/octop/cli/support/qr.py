"""Terminal QR code rendering (adapted from finnie channels_cmd)."""

from __future__ import annotations

import base64
import shutil
from io import BytesIO

import click
import httpx


def mask_secret(value: str) -> str:
    if not value:
        return "(empty)"
    if len(value) <= 4:
        return "****"
    return value[:4] + "****"


def _qr_matrix_from_image_bytes(img_bytes: bytes) -> list[list[int]] | None:
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        img = Image.open(BytesIO(img_bytes)).convert("L")
    except Exception:
        return None
    w, h = img.size
    if w <= 0 or h <= 0:
        return None
    px = img.load()
    if px is None:
        return None
    threshold = 128

    def is_dark(x: int, y: int) -> bool:
        raw = px[x, y]
        luma = sum(int(v) for v in raw) // len(raw) if isinstance(raw, tuple) else int(raw)
        return luma < threshold

    left = 0
    while left < w and not any(is_dark(left, y) for y in range(h)):
        left += 1
    right = w - 1
    while right > left and not any(is_dark(right, y) for y in range(h)):
        right -= 1
    top = 0
    while top < h and not any(is_dark(x, top) for x in range(w)):
        top += 1
    bottom = h - 1
    while bottom > top and not any(is_dark(x, bottom) for x in range(w)):
        bottom -= 1
    if right <= left or bottom <= top:
        return None
    inner_w = right - left + 1
    inner_h = bottom - top + 1
    runs: list[int] = []
    cur_dark = is_dark(left, top)
    run_len = 0
    for x in range(left, right + 1):
        d = is_dark(x, top)
        if d == cur_dark:
            run_len += 1
        else:
            runs.append(run_len)
            cur_dark = d
            run_len = 1
    runs.append(run_len)
    module_px = max(1, min(runs)) if runs else 1
    rows = max(1, round(inner_h / module_px))
    cols = max(1, round(inner_w / module_px))
    matrix: list[list[int]] = []
    for r in range(rows):
        cy = min(max(top + int((r + 0.5) * inner_h / rows), 0), h - 1)
        row_bits: list[int] = []
        for c in range(cols):
            cx = min(max(left + int((c + 0.5) * inner_w / cols), 0), w - 1)
            row_bits.append(1 if is_dark(cx, cy) else 0)
        matrix.append(row_bits)
    return matrix


def _render_qr_matrix(matrix: list[list[int]], border: int = 2) -> str:
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    total_rows = rows + 2 * border
    total_cols = cols + 2 * border
    if total_rows % 2 == 1:
        total_rows += 1

    def bit(r: int, c: int) -> int:
        rr, cc = r - border, c - border
        if 0 <= rr < rows and 0 <= cc < cols:
            return matrix[rr][cc]
        return 0

    reset = "\033[0m"
    lines: list[str] = []
    for r in range(0, total_rows, 2):
        parts: list[str] = []
        for c in range(total_cols):
            fg = 0 if bit(r, c) else 15
            bg = 0 if bit(r + 1, c) else 15
            parts.append(f"\033[38;5;{fg};48;5;{bg}m\u2580")
        parts.append(reset)
        lines.append("".join(parts))
    return reset + "\n".join(lines) + reset


def _print_url_fallback(url: str) -> None:
    click.secho(f"\n  Open this link to scan:\n  {url}\n", fg="cyan")


def render_qrcode_terminal(content: str) -> None:
    """Render a QR in the terminal, or fall back to printing the URL."""
    matrix: list[list[int]] | None = None
    display_url = content
    is_data_uri = content.startswith("data:image/")
    is_image_url = content.lower().split("?", 1)[0].endswith((".png", ".jpg", ".jpeg"))

    if is_data_uri or is_image_url:
        try:
            if is_data_uri:
                _, _, b64 = content.partition(",")
                img_bytes = base64.b64decode(b64)
            else:
                resp = httpx.get(content, timeout=15)
                resp.raise_for_status()
                img_bytes = resp.content
            matrix = _qr_matrix_from_image_bytes(img_bytes)
        except Exception:
            matrix = None
        if is_data_uri:
            display_url = "(embedded QR image)"

    if matrix is None and not (is_data_uri or is_image_url):
        try:
            import segno

            qr = segno.make(content, error="m")
            matrix = [list(row) for row in qr.matrix]
        except Exception:
            matrix = None

    if matrix is None:
        _print_url_fallback(content)
        return

    border = 2
    width_cols = len(matrix[0]) + 2 * border
    try:
        term_cols = shutil.get_terminal_size((80, 24)).columns
    except Exception:
        term_cols = 80
    if width_cols > term_cols:
        click.secho(
            f"  (QR is {width_cols} cols, terminal is {term_cols} — showing link only)",
            fg="yellow",
        )
        _print_url_fallback(display_url)
        return

    click.echo(_render_qr_matrix(matrix, border=border))
    if not is_data_uri:
        click.secho(f"\n  Link: {display_url}\n", fg="cyan")
