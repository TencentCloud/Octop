"""tests/unit/test_workspace_download.py"""

from __future__ import annotations

from octop.infra.gateway.media.backend_files import workspace_download_url


def test_workspace_download_url_outbound_and_absolute() -> None:
    url = workspace_download_url("agent-1", "outbound/chart.png")
    assert "path=outbound%2Fchart.png" in url
    abs_url = workspace_download_url("agent-1", "/Users/me/x.png")
    assert "path=%2FUsers%2Fme%2Fx.png" in abs_url
    file_url = workspace_download_url("agent-1", "file:///root/.octop/agents/main/generated/a.pptx")
    assert "path=file%3A%2F%2F%2Froot%2F.octop%2Fagents%2Fmain%2Fgenerated%2Fa.pptx" in file_url
