from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from PIL import Image

from bot.keyboards import category_keyboard, menu_keyboard, photo_upload_keyboard, wardrobe_view_keyboard
from bot.storage import (
    add_item,
    delete_item_by_id,
    get_category_counts,
    get_items,
    update_display_name,
    update_item_metadata,
    update_processed_file_id,
)
from bot.states import BotStates
from services.ai_analyze_service import AIAnalyzeService, build_russian_item_summary

router = Router()

CATEGORIES = {
    "top": "👕 Верх",
    "bottom": "👖 Низ",
    "outerwear": "🧥 Верхняя одежда",
    "shoes": "👟 Обувь",
    "accessory": "🧢 Аксессуары",
    "onepiece": "👔 Цельный образ",
}

CATEGORY_ALIASES = {
    "верх": "top",
    "👕 верх": "top",
    "низ": "bottom",
    "👖 низ": "bottom",
    "верхняя одежда": "outerwear",
    "🧥 верхняя одежда": "outerwear",
    "обувь": "shoes",
    "👟 обувь": "shoes",
    "аксессуар": "accessory",
    "аксессуары": "accessory",
    "🧢 аксессуары": "accessory",
    "платье": "onepiece",
    "цельный образ": "onepiece",
    "👔 цельный образ": "onepiece",
    "top": "top",
    "bottom": "bottom",
    "outerwear": "outerwear",
    "shoes": "shoes",
    "accessory": "accessory",
    "dress": "onepiece",
    "onepiece": "onepiece",
}


def normalize_category(text: str) -> str | None:
    cleaned = (text or "").strip().lower()
    return CATEGORY_ALIASES.get(cleaned)


def _item_actions_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"item:delete:{item_id}"),
                InlineKeyboardButton(text="✏️ Переименовать", callback_data=f"item:rename:{item_id}"),
            ],
            [
                InlineKeyboardButton(text="✨ Улучшить фото", callback_data=f"item:enhance:{item_id}"),
            ],
        ]
    )


def _confirm_delete_keyboard(item_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Удалить", callback_data=f"item:delete_confirm:{item_id}"),
                InlineKeyboardButton(text="↩️ Отмена", callback_data=f"item:delete_cancel:{item_id}"),
            ]
        ]
    )


def _item_title(item: dict[str, str | int | None]) -> str:
    display_name = item.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()

    item_type = (item.get("type") or "unknown").strip()
    primary_color = (item.get("primary_color") or "unknown").strip()
    if item_type != "unknown" and primary_color != "unknown":
        return f"{primary_color} {item_type}"
    if item_type != "unknown":
        return item_type
    if primary_color != "unknown":
        return primary_color
    return "вещь без названия"


def _build_item_caption(item: dict[str, str | int | None]) -> str:
    category_name = CATEGORIES.get(str(item.get("category") or ""), str(item.get("category") or ""))
    return f"{category_name} — {_item_title(item)}"


def _build_enhanced_image(image_bytes: bytes) -> bytes | None:
    if not image_bytes:
        return None

    source = Image.open(BytesIO(image_bytes)).convert("RGBA")
    width, height = source.size
    px = source.load()

    corners = [px[0, 0], px[width - 1, 0], px[0, height - 1], px[width - 1, height - 1]]
    avg_r = sum(pixel[0] for pixel in corners) // 4
    avg_g = sum(pixel[1] for pixel in corners) // 4
    avg_b = sum(pixel[2] for pixel in corners) // 4

    for y in range(height):
        for x in range(width):
            r, g, b, a = px[x, y]
            distance = abs(r - avg_r) + abs(g - avg_g) + abs(b - avg_b)
            if distance < 42:
                px[x, y] = (r, g, b, 0)
            else:
                px[x, y] = (r, g, b, a)

    bbox = source.getbbox()
    if not bbox:
        return None

    cropped = source.crop(bbox)
    target_size = int(max(cropped.width, cropped.height) * 1.25)
    canvas = Image.new("RGB", (target_size, target_size), (245, 245, 245))
    offset_x = (target_size - cropped.width) // 2
    offset_y = (target_size - cropped.height) // 2
    canvas.paste(cropped, (offset_x, offset_y), cropped)

    output = BytesIO()
    canvas.save(output, format="JPEG", quality=95)
    return output.getvalue()


async def _render_wardrobe_cards(message: Message, user_id: int) -> None:
    items = get_items(user_id)
    if not items:
        await message.answer("Гардероб пока пуст. Нажмите '📥 Добавить вещь' и добавьте вещи.")
        return

    counts = get_category_counts(user_id)
    lines = ["Ваш гардероб:"]
    for category, count in sorted(counts.items()):
        lines.append(f"- {CATEGORIES.get(category, category)}: {count}")
    await message.answer("\n".join(lines))

    for item in items:
        preview_file_id = item.get("processed_file_id") or item.get("telegram_file_id")
        caption = _build_item_caption(item)
        if preview_file_id:
            await message.answer_photo(
                photo=str(preview_file_id),
                caption=caption,
                reply_markup=_item_actions_keyboard(int(item["id"])),
            )
        else:
            await message.answer(
                f"📸 Фото недоступно\n{caption}",
                reply_markup=_item_actions_keyboard(int(item["id"])),
            )


@router.message(F.text == "📸 Загрузить гардероб")
async def upload_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.upload_category)
    await message.answer("Выберите категорию:", reply_markup=category_keyboard())


@router.message(F.text.in_({"📥 Загрузить", "Загрузить", "📥 Добавить вещь"}))
async def upload_start_short(message: Message, state: FSMContext) -> None:
    await upload_start(message, state)
