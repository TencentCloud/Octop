"""Office → PDF preview conversion (LibreOffice Kit helper)."""

from __future__ import annotations

from octop.infra.office_preview.formats import (
    CONVERTIBLE_EXTENSIONS,
    extension_of,
    is_convertible_filename,
)
from octop.infra.office_preview.runtime import KIT_VERSION, probe_runtime
from octop.infra.office_preview.service import (
    ConvertedPdf,
    OfficePreviewService,
    get_office_preview_service,
    reset_office_preview_service,
)

__all__ = [
    "CONVERTIBLE_EXTENSIONS",
    "ConvertedPdf",
    "KIT_VERSION",
    "OfficePreviewService",
    "extension_of",
    "get_office_preview_service",
    "is_convertible_filename",
    "probe_runtime",
    "reset_office_preview_service",
]
