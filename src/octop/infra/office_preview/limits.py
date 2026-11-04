"""Hard limits for Office → PDF conversion (first-wave, low concurrency)."""

from __future__ import annotations

MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 80 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
CONVERT_TIMEOUT_SECONDS = 90.0
MAX_CONCURRENCY = 1
MAX_WAITING = 8
CACHE_TTL_SECONDS = 300.0
CACHE_MAX_ITEMS = 16
ENGINE_ID = "libreoffice-kit@0.2.3:pdf"
