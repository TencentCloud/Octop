"""City weather via Open-Meteo (no API key)."""

from __future__ import annotations

import json
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_WMO: dict[int, str] = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    95: "雷暴",
    96: "雷暴伴冰雹",
    99: "强雷暴伴冰雹",
}


_WMO_ICON: dict[int, str] = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌧️",
    55: "🌧️",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    71: "🌨️",
    73: "❄️",
    75: "❄️",
    80: "🌦️",
    81: "🌧️",
    82: "🌧️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}


def _wmo_label(code: object) -> str:
    try:
        n = int(code)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "未知"
    return _WMO.get(n, f"天气码 {n}")


def _wmo_icon(code: object) -> str:
    try:
        n = int(code)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "🌡️"
    if n in _WMO_ICON:
        return _WMO_ICON[n]
    if n <= 2:
        return "🌤️"
    if n <= 3:
        return "☁️"
    if 50 <= n < 70:
        return "🌧️"
    if 70 <= n < 80:
        return "❄️"
    if n >= 90:
        return "⛈️"
    return "🌡️"


def _payload(renderer: str, data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": renderer, "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _client() -> httpx.Client:
    return httpx.Client(timeout=15.0, follow_redirects=True)


def _geocode(city: str) -> dict[str, Any] | None:
    with _client() as client:
        resp = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh"},
        )
        resp.raise_for_status()
        payload = resp.json()
    results = payload.get("results") or []
    if not results or not isinstance(results[0], dict):
        return None
    return results[0]


def _forecast(lat: float, lon: float, days: int) -> dict[str, Any]:
    with _client() as client:
        resp = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,relative_humidity_2m",
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
                "forecast_days": days,
                "timezone": "auto",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_weather(city: str, days: int = 3) -> str:
    """Look up current weather and a short daily forecast for a city."""
    city = (city or "").strip()
    if not city:
        return _payload(
            "weather_card",
            {"error": "city is required"},
            "请提供城市名称，例如「北京」或「Tokyo」。",
        )
    day_n = max(1, min(int(days or 3), 7))
    try:
        place = _geocode(city)
        if place is None:
            return _payload(
                "weather_card",
                {"city": city, "error": "city not found"},
                f"未找到城市「{city}」。",
            )
        lat = float(place["latitude"])
        lon = float(place["longitude"])
        raw = _forecast(lat, lon, day_n)
    except Exception as exc:
        return _payload(
            "weather_card",
            {"city": city, "error": str(exc)},
            f"天气查询失败：{exc}",
        )

    current = raw.get("current") or {}
    daily = raw.get("daily") or {}
    code = current.get("weather_code")
    name = str(place.get("name") or city)
    country = str(place.get("country") or "")
    cur_label = _wmo_label(code)
    temp = current.get("temperature_2m")
    daily_rows: list[dict[str, Any]] = []
    dates = list(daily.get("time") or [])
    for i, date in enumerate(dates[:day_n]):
        wcode = (daily.get("weather_code") or [None])[i] if daily.get("weather_code") else None
        daily_rows.append(
            {
                "date": date,
                "t_max": (daily.get("temperature_2m_max") or [None])[i],
                "t_min": (daily.get("temperature_2m_min") or [None])[i],
                "precip": (daily.get("precipitation_probability_max") or [None])[i],
                "weather_code": wcode,
                "label": _wmo_label(wcode),
                "icon": _wmo_icon(wcode),
            },
        )
    data = {
        "city": name,
        "country": country,
        "latitude": lat,
        "longitude": lon,
        "current": {
            "temp": temp,
            "weather_code": code,
            "wind": current.get("wind_speed_10m"),
            "humidity": current.get("relative_humidity_2m"),
            "label": cur_label,
            "icon": _wmo_icon(code),
        },
        "daily": daily_rows,
    }
    text = f"{_wmo_icon(code)} {name} {country} · {cur_label} {temp}°C"
    if daily_rows:
        text += "；" + "，".join(
            f"{row['date'][5:]} {row['t_min']}~{row['t_max']}°C" for row in daily_rows[:3]
        )
    return _payload("weather_card", data, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "get_weather",
        get_weather,
        description=(
            "查询城市当前天气与未来几天预报。参数 city 为城市名（如 北京、Shanghai），"
            "days 为预报天数（1–7，默认 3）。"
        ),
    )
