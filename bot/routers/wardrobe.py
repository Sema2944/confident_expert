from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.states import BotStates

router = Router()

CATEGORIES = {
    "top": "Верх",
    "bottom": "Низ",
    "outerwear": "Верхняя одежда",
    "shoes": "Обувь",
    "accessory": "Аксессуар",
    "dress": "Платье",
}


@router.message(F.text == "📸 Загрузить гардероб")
async def upload_start(message: Message, state: FSMContext) -> None:
    await state.set_state(BotStates.upload_category)
    options = "\n".join([f"- {value}" for value in CATEGORIES.values()])
    await message.answer(f"Выберите категорию:\n{options}")


@router.message(BotStates.upload_category, F.text)
async def set_category(message: Message, state: FSMContext) -> None:
    mapping = {value: key for key, value in CATEGORIES.items()}
    category = mapping.get(message.text)
    if not category:
        await message.answer("Не понял категорию, попробуйте снова.")
        return
    await state.update_data(category=category)
    await state.set_state(BotStates.upload_photos)
    await message.answer("Пришлите фото вещи.")


@router.message(BotStates.upload_photos, F.photo)
async def upload_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    category = data.get("category")
    file_id = message.photo[-1].file_id
    await message.answer(
        f"Фото сохранено (категория: {category}, file_id: {file_id})."
    )
    await state.set_state(BotStates.menu)


@router.message(BotStates.upload_photos)
async def upload_photo_prompt(message: Message) -> None:
    await message.answer("Нужно отправить фото.")
