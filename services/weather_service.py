"""Погода для подбора: коротко спрашиваем, кэшируем, не блокируем образ."""

import logging
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

# Кэш по городу: ключ -> (температура, когда измерили)
_weather_cache: dict[str, tuple[float, datetime]] = {}
_CACHE_TTL = timedelta(minutes=30)
_REFRESH_EVERY = timedelta(minutes=30)
# Два источника подряд, каждый не дольше 1.5 с — вместе не больше 3 секунд.
SOURCE_TIMEOUT = 1.5
_last_refresh_at: datetime | None = None

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


def cache_key(city: str | None, lat: float, lon: float) -> str:
    name = (city or "").strip().lower().replace("ё", "е")
    if name:
        return f"city:{name}"
    return f"coord:{lat:.2f},{lon:.2f}"


def clear_weather_cache() -> None:
    global _last_refresh_at
    _weather_cache.clear()
    _last_refresh_at = None


def refresh_interval_elapsed(last: datetime | None, now: datetime) -> bool:
    return last is None or now - last >= _REFRESH_EVERY


def _same_day(left: datetime, right: datetime) -> bool:
    return left.date() == right.date()


def _remember(key: str, temp: float, when: datetime) -> float:
    _weather_cache[key] = (temp, when)
    return temp


async def _read_open_meteo(client: httpx.AsyncClient, lat: float, lon: float) -> float:
    resp = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "current_weather": "true"},
    )
    resp.raise_for_status()
    return float(resp.json()["current_weather"]["temperature"])


async def _read_wttr(client: httpx.AsyncClient, lat: float, lon: float) -> float:
    resp = await client.get(
        f"https://wttr.in/{lat},{lon}",
        params={"format": "j1"},
        headers={"User-Agent": "wardrobe-bot"},
    )
    resp.raise_for_status()
    return float(resp.json()["current_condition"][0]["temp_C"])


async def get_current_temperature(
    lat: float,
    lon: float,
    city: str | None = None,
) -> float | None:
    """Температура за сегодня. Свежий кэш 30 минут, иначе Open-Meteo и wttr.in."""
    key = cache_key(city, lat, lon)
    now = datetime.now()
    cached = _weather_cache.get(key)
    if cached and now - cached[1] < _CACHE_TTL and _same_day(cached[1], now):
        return cached[0]

    fetched: float | None = None
    try:
        async with httpx.AsyncClient(timeout=SOURCE_TIMEOUT) as client:
            try:
                fetched = await _read_open_meteo(client, lat, lon)
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                if code == 429:
                    logger.warning("Open-Meteo rate limited (429) for %s", key)
                else:
                    logger.warning("Open-Meteo HTTP %s for %s", code, key)
            except Exception as exc:
                logger.warning("Open-Meteo unavailable for %s: %s", key, type(exc).__name__)
            if fetched is None:
                try:
                    fetched = await _read_wttr(client, lat, lon)
                    logger.info("Weather for %s taken from wttr.in", key)
                except Exception as exc:
                    logger.warning("wttr.in unavailable for %s: %s", key, type(exc).__name__)
    except Exception as exc:
        logger.warning("Weather client failed for %s: %s", key, type(exc).__name__)

    if fetched is not None:
        return _remember(key, fetched, now)
    if cached and _same_day(cached[1], now):
        logger.info("Weather for %s uses last reading from today", key)
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
        "winter": "Погоду уточнить не удалось, подбираю зимний образ по сезону.",
        "demi": "Погоду уточнить не удалось, подбираю демисезонный образ по сезону.",
        "summer": "Погоду уточнить не удалось, подбираю летний образ по сезону.",
    }
    return season, fallback_msg[season]


async def detect_season_for_user(user_id: int) -> tuple[str, str]:
    """Сезон по погоде. Если замера нет совсем, образ всё равно собирается по календарю."""
    try:
        from bot.storage import get_user_location

        city, lat, lon = await get_user_location(user_id)
        if not (lat and lon):
            lat, lon = CITY_COORDS.get((city or "").strip().lower(), DEFAULT_COORDS)
        temp = await get_current_temperature(lat, lon, city=city)
    except Exception as exc:
        logger.warning("Season detection failed for user %s: %s", user_id, type(exc).__name__)
        return _season_without_temperature()

    if temp is None:
        return _season_without_temperature()

    season = temperature_to_season(temp)
    message = SEASON_WEATHER_TEXT[season].format(temp=round(temp))
    return season, message


async def refresh_active_cities() -> int:
    """Обновляет кэш погоды по городам пользователей. Свежие значения не трогает."""
    from bot.storage import list_weather_places

    places = await list_weather_places()
    refreshed = 0
    for place in places:
        city = place.get("city") or "Москва"
        lat = place.get("lat")
        lon = place.get("lon")
        if lat is None or lon is None:
            lat, lon = CITY_COORDS.get(city.strip().lower(), DEFAULT_COORDS)
        before = _weather_cache.get(cache_key(city, float(lat), float(lon)))
        temp = await get_current_temperature(float(lat), float(lon), city=city)
        after = _weather_cache.get(cache_key(city, float(lat), float(lon)))
        if temp is not None and after is not before:
            refreshed += 1
    logger.info("Weather refresh: cities=%s updated=%s", len(places), refreshed)
    return refreshed


async def maybe_refresh_active_cities(now: datetime | None = None) -> bool:
    """True, если фоновое обновление пора запускать (раз в 30 минут)."""
    global _last_refresh_at
    now = now or datetime.now()
    if not refresh_interval_elapsed(_last_refresh_at, now):
        return False
    await refresh_active_cities()
    _last_refresh_at = now
    return True


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
