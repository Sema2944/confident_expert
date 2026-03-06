from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import location_request_keyboard, menu_keyboard
from bot.states import BotStates
from bot.storage import get_items, get_user_location, set_user_location
from bot.utils.messages import HELP_MESSAGE, START_MESSAGE
from services.wardrobe_analysis_service import analyze_wardrobe_gaps

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    from services.subscription_service import get_or_create_user, activate_subscription
    user = await get_or_create_user(message.from_user.id, message.from_user.username)

    from config.settings import settings
    if settings.admin_id and message.from_user.id == settings.admin_id:
        await activate_subscription(message.from_user.id, 365)

    from bot.storage import is_first_start
    if await is_first_start(message.from_user.id):
        try:
            from services.admin_notify_service import AdminNotifyService
            username = f"@{message.from_user.username}" if message.from_user.username else str(message.from_user.id)
            await AdminNotifyService.notify(
                message.bot,
                f"👤 <b>Новый пользователь</b>\n{username} (id: {message.from_user.id})",
            )
        except Exception:
            pass

    city, lat, lon = await get_user_location(message.from_user.id)

    # Первый запуск — нет координат и город дефолтный
    if not lat and city == "Москва" and user.get("outfit_requests_count", 0) == 0:
        await state.set_state(BotStates.setting_city)
        await message.answer(
            f"{START_MESSAGE}\n\n"
            "📍 Где ты? Отправь геолокацию или напиши город —\n"
            "я буду подбирать одежду по реальной погоде.",
            reply_markup=location_request_keyboard(),
        )
        return

    items = await get_items(message.from_user.id)
    if not items:
        await message.answer(
            f"{START_MESSAGE}\n\nКогда загрузишь вещи, нажми '✨ Собрать образ' для первого образа.",
            reply_markup=menu_keyboard(),
        )
        return

    gaps = analyze_wardrobe_gaps(items)
    if gaps:
        await message.answer(f"{START_MESSAGE}\n\n{gaps}", reply_markup=menu_keyboard())
    else:
        await message.answer(START_MESSAGE, reply_markup=menu_keyboard())


@router.message(Command("city"))
async def cmd_set_city(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.setting_city)
    await message.answer(
        "📍 Где ты сейчас?\n\n"
        "Отправь геолокацию (самый точный вариант) или напиши город текстом.",
        reply_markup=location_request_keyboard(),
    )


@router.message(BotStates.setting_city, F.location)
async def handle_location(message: Message, state: FSMContext) -> None:
    lat = message.location.latitude
    lon = message.location.longitude

    from services.weather_service import get_current_temperature, reverse_geocode, temperature_to_season
    city_name = await reverse_geocode(lat, lon)

    await set_user_location(message.from_user.id, city_name, lat, lon)
    await state.set_state(BotStates.menu)

    temp = await get_current_temperature(lat, lon)
    temp_text = f" ({round(temp)}°C)" if temp is not None else ""

    await message.answer(
        f"📍 Локация: {city_name}{temp_text}\n"
        "Теперь подбираю образы по реальной погоде!",
        reply_markup=menu_keyboard(),
    )


@router.message(BotStates.setting_city, F.text)
async def handle_city_text(message: Message, state: FSMContext) -> None:
    if message.text == "⬅️ Пропустить (Москва)":
        city = "Москва"
    else:
        city = message.text.strip()

    from services.weather_service import CITY_COORDS
    coords = CITY_COORDS.get(city.lower())
    if coords:
        await set_user_location(message.from_user.id, city, coords[0], coords[1])
    else:
        await set_user_location(message.from_user.id, city)

    await state.set_state(BotStates.menu)
    await message.answer(
        f"📍 Город: {city}\nТеперь подбираю образы по реальной погоде!",
        reply_markup=menu_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Меню", reply_markup=menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_MESSAGE)


@router.message(Command("admin_premium"))
async def admin_premium(message: Message) -> None:
    from config.settings import settings
    if not settings.admin_id or message.from_user.id != settings.admin_id:
        return
    from services.subscription_service import activate_subscription
    await activate_subscription(message.from_user.id, 365)
    await message.answer("✅ Премиум на 365 дней активирован.")
