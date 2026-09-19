"""Air quality via Open-Meteo geocoding + air-quality API."""

from __future__ import annotations

import json
from typing import Any

import httpx
from harness_agent.plugins import PluginContext


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "air_quality_card", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _aqi_label(aqi: float | None) -> str:
    if aqi is None:
        return "—"
    v = float(aqi)
    if v <= 50:
        return "优"
    if v <= 100:
        return "良"
    if v <= 150:
        return "轻度"
    if v <= 200:
        return "中度"
    return "重度"


def _resolve_coords(
    client: httpx.Client,
    city: str,
    lat: float | None,
    lon: float | None,
) -> tuple[float, float, str]:
    if lat is not None and lon is not None:
        return float(lat), float(lon), city or f"{lat},{lon}"
    name = (city or "Beijing").strip()
    resp = client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": name, "count": 1, "language": "zh"},
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        raise ValueError(f"未找到城市：{name}")
    row = results[0]
    label = str(row.get("name") or name)
    country = str(row.get("country") or "")
    if country:
        label = f"{label}, {country}"
    return float(row["latitude"]), float(row["longitude"]), label


async def get_air_quality(
    city: str = "Beijing",
    lat: float | None = None,
    lon: float | None = None,
) -> str:
    """Fetch current PM2.5/PM10 and AQI for a city or coordinates."""
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            latitude, longitude, place = _resolve_coords(client, city, lat, lon)
            resp = client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": "pm2_5,pm10,european_aqi,us_aqi",
                },
            )
            resp.raise_for_status()
            current = resp.json().get("current") or {}
    except Exception as exc:
        return _payload({"error": str(exc)}, f"空气质量查询失败：{exc}")
    pm25 = current.get("pm2_5")
    pm10 = current.get("pm10")
    us_aqi = current.get("us_aqi")
    eu_aqi = current.get("european_aqi")
    aqi = us_aqi if us_aqi is not None else eu_aqi
    label = _aqi_label(float(aqi) if aqi is not None else None)
    data = {
        "city": place,
        "latitude": latitude,
        "longitude": longitude,
        "pm2_5": pm25,
        "pm10": pm10,
        "us_aqi": us_aqi,
        "european_aqi": eu_aqi,
        "aqi_label": label,
    }
    text = f"{place} 空气质量 {label} · PM2.5 {pm25} · AQI {aqi}"
    return _payload(data, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "get_air_quality",
        get_air_quality,
        description="查询空气质量。city 默认 Beijing；也可传 lat/lon 坐标。",
    )
