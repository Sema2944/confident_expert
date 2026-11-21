"""Определение сезона по реальной погоде через Open-Meteo (бесплатно, без ключа)."""

import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# Кэш: {cache_key: (temperature, timestamp)}
_weather_cache: dict[str, tuple[float, datetime]] = {}
_CACHE_TTL = timedelta(minutes=30)

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


def clear_weather_cache() -> None:
    _weather_cache.clear()


async def get_current_temperature(lat: float, lon: float) -> float | None:
    """Температура Open-Meteo. Свежий кэш 30 минут, при ошибке — прошлое значение."""
    cache_key = f"{lat:.2f},{lon:.2f}"
    now = datetime.now()
    cached = _weather_cache.get(cache_key)

    if cached and now - cached[1] < _CACHE_TTL:
        return cached[0]

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
            temp = float(data["current_weather"]["temperature"])
            _weather_cache[cache_key] = (temp, now)
            return temp
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        if code == 429:
            logger.warning("Open-Meteo rate limited (429) for %s", cache_key)
        else:
            logger.warning("Open-Meteo HTTP %s for %s", code, cache_key)
    except Exception as exc:
        logger.warning("Open-Meteo unavailable for %s: %s", cache_key, type(exc).__name__)

    if cached:
        logger.info("Open-Meteo using last known temperature for %s", cache_key)
        return cached[0]
    return None


def temperature_to_season(temp: float) -> str:
    """Маппинг температуры → сезон для подбора одежды."""
    if temp < 5:
        return "winter"
    elif temp <= 17:
        return "demi"
    else:
        return "summer"


SEASON_WEATHER_TEXT: dict[str, str] = {
    "winter": "❄️ На улице {temp}°C — подбираю тёплый образ",
    "demi": "🍂 На улице {temp}°C — подбираю демисезонный образ",
    "summer": "☀️ На улице {temp}°C — подбираю лёгкий образ",
}


def _fallback_season() -> str:
    """Определение сезона по текущему месяцу (fallback если API недоступен)."""
    month = datetime.now().month
    if month in (12, 1, 2, 3):  # декабрь-март
        return "winter"
    elif month in (4, 5, 9, 10, 11):  # апрель-май, сентябрь-ноябрь
        return "demi"
    else:  # июнь-август
        return "summer"


def _season_without_temperature() -> tuple[str, str]:
    season = _fallback_season()
    fallback_msg = {
        "winter": "❄️ Подбираю зимний образ",
        "demi": "🍂 Подбираю демисезонный образ",
        "summer": "☀️ Подбираю лёгкий образ",
    }
    return season, fallback_msg[season]


async def detect_season_for_user(user_id: int) -> tuple[str, str]:
    """Сезон по погоде. Ошибка погоды не мешает подбору: календарь или прошлый замер."""
    try:
        from bot.storage import get_user_location

        city, lat, lon = await get_user_location(user_id)
        if lat and lon:
            temp = await get_current_temperature(lat, lon)
        else:
            coords = CITY_COORDS.get((city or "").strip().lower(), DEFAULT_COORDS)
            temp = await get_current_temperature(*coords)
    except Exception as exc:
        logger.warning("Season detection failed for user %s: %s", user_id, type(exc).__name__)
        return _season_without_temperature()

    if temp is None:
        return _season_without_temperature()

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
