"""Определение сезона по реальной погоде через Open-Meteo (бесплатно, без ключа)."""

import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# Кэш: {cache_key: (temperature, timestamp)}
_weather_cache: dict[str, tuple[float, datetime]] = {}
_CACHE_TTL = timedelta(hours=2)

# Координаты основных городов (fallback если пользователь не указал город)
CITY_COORDS: dict[str, tuple[float, float]] = {
    "москва": (55.7558, 37.6173),
    "санкт-петербург": (59.9343, 30.3351),
    "новосибирск": (55.0084, 82.9357),
    "екатеринбург": (56.8389, 60.6057),
    "казань": (55.7961, 49.1064),
    "нижний новгород": (56.2965, 43.9361),
    "краснодар": (45.0355, 38.9753),
    "сочи": (43.6028, 39.7342),
    "ростов-на-дону": (47.2357, 39.7015),
    "владивосток": (43.1155, 131.8855),
}
DEFAULT_COORDS = (55.7558, 37.6173)  # Москва


async def get_current_temperature(lat: float, lon: float) -> float | None:
    """Получить текущую температуру через Open-Meteo (бесплатно, без ключа)."""
    cache_key = f"{lat:.2f},{lon:.2f}"
    now = datetime.now()

    if cache_key in _weather_cache:
        temp, cached_at = _weather_cache[cache_key]
        if now - cached_at < _CACHE_TTL:
            return temp

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": "true",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            temp = data["current_weather"]["temperature"]
            _weather_cache[cache_key] = (temp, now)
            return temp
    except Exception:
        logger.exception("Failed to get weather from Open-Meteo")
        return None


def temperature_to_season(temp: float) -> str:
    """Маппинг температуры → сезон для подбора одежды."""
    if temp <= 0:
        return "winter"
    elif temp <= 15:
        return "demi"
    else:
        return "summer"


SEASON_WEATHER_TEXT: dict[str, str] = {
    "winter": "❄️ На улице {temp}°C — подбираю тёплый образ",
    "demi": "🍂 На улице {temp}°C — подбираю демисезонный образ",
    "summer": "☀️ На улице {temp}°C — подбираю лёгкий образ",
}


async def detect_season_for_user(user_id: int) -> tuple[str, str]:
    """Определить сезон для пользователя.

    Приоритет: координаты (геолокация) → город из справочника → Москва.
    Возвращает (season_code, weather_message).
    """
    from bot.storage import get_user_location

    city, lat, lon = await get_user_location(user_id)

    if lat and lon:
        temp = await get_current_temperature(lat, lon)
    else:
        coords = CITY_COORDS.get((city or "").strip().lower(), DEFAULT_COORDS)
        temp = await get_current_temperature(*coords)

    if temp is None:
        month = datetime.now().month
        if month in (12, 1, 2):
            return "winter", "❄️ Подбираю зимний образ"
        elif month in (3, 4, 5, 9, 10, 11):
            return "demi", "🍂 Подбираю демисезонный образ"
        else:
            return "summer", "☀️ Подбираю лёгкий образ"

    season = temperature_to_season(temp)
    message = SEASON_WEATHER_TEXT[season].format(temp=round(temp))
    return season, message


async def reverse_geocode(lat: float, lon: float) -> str:
    """Определить название города по координатам через Nominatim."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "accept-language": "ru"},
                headers={"User-Agent": "WardrobeBot/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            city = (
                data.get("address", {}).get("city")
                or data.get("address", {}).get("town")
                or data.get("address", {}).get("village")
                or data.get("address", {}).get("state")
                or "Неизвестный город"
            )
            return city
    except Exception:
        logger.exception("Reverse geocoding failed")
        return "Неизвестный город"
