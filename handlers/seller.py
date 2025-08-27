from aiogram import Router, F, types
from aiogram.types import Message, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, \
    KeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.formatting import as_marked_section, Bold
import asyncio
import logging


from database import async_session
from models import Lot, LotImage, LotStatus
from states import SellerStates
from config import settings
from auctions.logic import start_auction

from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = Router()

def is_unique_photo(file_bytes: bytes, existing_hashes: set) -> bool:
    import hashlib
    photo_hash = hashlib.md5(file_bytes).hexdigest()
    if photo_hash in existing_hashes:
        return False
    existing_hashes.add(photo_hash)
    return True

async def return_to_preview(message: Message, state: FSMContext):
    await show_confirmation(message, state)

DEVICE_MODELS = {
    # iPhone (X и дальше)
    "iPhone X": 51000,            # медиана ~85 000 ₸ → 60%
    "iPhone XR": 54000,           # медиана ~90 000 ₸ → 60%
    "iPhone XS": 60000,           # медиана ~100 000 ₸ → 60%
    "iPhone XS Max": 63000,       # медиана ~105 000 ₸ → 60%
    "iPhone 11": 60000,           # медиана ~100 000 ₸ → 60% :contentReference[oaicite:0]{index=0}
    "iPhone 11 Pro": 72000,       # оценка (характерно дороже, ~120 000 ₸)
    "iPhone 11 Pro Max": 90000,   # оценка, медиана ~150 000 ₸

    "iPhone 12": 90000,           # оценка: мед. ~150 000 ₸
    "iPhone 12 mini": 84000,      # оценка
    "iPhone 12 Pro": 96000,       # оценка
    "iPhone 12 Pro Max": 102000,  # оценка

    "iPhone 13": 90000,           # медиана ~150 000 ₸ → 60%
    "iPhone 13 mini": 81000,      # оценка
    "iPhone 13 Pro": 102000,      # оценка
    "iPhone 13 Pro Max": 108000,  # оценка

    "iPhone 14": 126000,          # медиана ~210 000 ₸ → 60%
    "iPhone 14 Plus": 120000,     # оценка
    "iPhone 14 Pro": 132000,      # оценка
    "iPhone 14 Pro Max": 138000,  # оценка

    "iPhone 15": 180000,          # оценка
    "iPhone 15 Plus": 186000,     # оценка
    "iPhone 15 Pro": 192000,      # оценка
    "iPhone 15 Pro Max": 198000,  # оценка

    # Samsung Galaxy S-серия
    "Samsung S8": 42000,          # оценка 60% от ~70 000 ₸
    "Samsung S8+": 45000,
    "Samsung S9": 48000,
    "Samsung S9+": 51000,
    "Samsung S10": 54000,
    "Samsung S10+": 60000,
    "Samsung S10e": 48000,

    "Samsung S20": 82000,         # медиана ~137 000 ₸ → 60% :contentReference[oaicite:1]{index=1}
    "Samsung S20+": 84000,
    "Samsung S20 Ultra": 102000,
    "Samsung S21": 54000,         # медиана ~90 000 ₸ → 60%
    "Samsung S21+": 57000,
    "Samsung S21 Ultra": 60000,

    "Samsung S22": 96000,         # оценка
    "Samsung S22+": 102000,
    "Samsung S22 Ultra": 108000,

    "Samsung S23": 120000,        # оценка
    "Samsung S23+": 126000,
    "Samsung S23 Ultra": 132000,

    "Samsung S24": 150000,        # оценка
    "Samsung S24+": 156000,
    "Samsung S24 Ultra": 288000,  # медиана ~480 000 ₸ → 60% :contentReference[oaicite:2]{index=2}

    # Samsung Note (>=2019)
    "Note10": 60000,              # оценка ~100 000 ₸ → 60%
    "Note10+": 66000,
    "Note20": 84000,
    "Note20 Ultra": 108000,

    # Samsung A-series (>=2019)
    "Samsung A10s": 30000,        # оценка ~50 000 ₸ → 60%
    "Samsung A20s": 33000,
    "Samsung A30s": 36000,
    "Samsung A40": 39000,
    "Samsung A50": 42000,
    "Samsung A51": 45000,
    "Samsung A52": 48000,
    "Samsung A70": 54000,
    "Samsung A71": 57000,
    "Samsung A72": 60000,
    "Samsung A80": 66000,
    "Samsung A90": 72000,
}


# reply keyboard (fallback / главное меню)
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Хочу продать"), KeyboardButton(text="📋 Список аукционов")],
        [KeyboardButton(text="ℹ️ Правила"), KeyboardButton(text="📞 Поддержка")]
    ],
    resize_keyboard=True
)



# ---------- Start selling ----------
@router.message(Command("sell"))
@router.message(F.text == "📤 Хочу продать")
async def start_selling(message: Message, state: FSMContext):
    await message.answer(

        "ℹ️ Аукцион — это быстрый способ выгодно продать телефон.\n\n\n"
        "📱 УСЛОВИЯ ДЛЯ ПРОДАВЦА\n"
        "1. Разрешается выставлять только телефоны, законно принадлежащие вам.\n\n"
        "2. Вы несете ответственность за законность и соответствие описанию товара.(модель, фото, IMEI, состояние).\n\n"
        "3. Сделка и расчёты происходят напрямую с победителем аукциона (покупателем).\n\n"
        "4.Использование Telegram-бота означает согласие с условиями Оферты (смотреть в разделе Правила).\n\n\n"
        "❗ После публикации изменить лот будет нельзя!"
    )
    """Начало продажи — показать выбор модели"""
    await show_model_keyboard(message)
    await state.set_state(SellerStates.title)

async def show_model_keyboard(message_or_callback, edit: bool = False):
    """Показать клавиатуру с моделями. Если edit=True и передан CallbackQuery — редактируем сообщение."""
    buttons = []
    row = []
    for i, model in enumerate(DEVICE_MODELS, start=1):
        row.append(InlineKeyboardButton(text=model, callback_data=f"model_{model}"))
        if i % 2 == 0 or i == len(DEVICE_MODELS):
            buttons.append(row)
            row = []

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    try:
        if edit and isinstance(message_or_callback, types.CallbackQuery) and message_or_callback.message:
            # пытаемся отредактировать существующее сообщение
            await message_or_callback.message.edit_text("📱 Выберите модель устройства:", reply_markup=kb)
        else:
            await message_or_callback.answer("📱 Выберите модель устройства:", reply_markup=kb)
    except Exception as e:
        # если не удалось отредактировать (сообщение удалено), просто отправим новое
        logger.debug("show_model_keyboard: edit failed, sending new message", exc_info=e)
        await message_or_callback.answer("📱 Выберите модель устройства:", reply_markup=kb)

# ---------- Model selected ----------
@router.callback_query(F.data.startswith("model_"))
async def model_selected(callback: types.CallbackQuery, state: FSMContext):
    model_name = callback.data.split("model_", 1)[1]
    start_price = DEVICE_MODELS.get(model_name)
    if start_price is None:
        await callback.answer("❌ Неизвестная модель.", show_alert=True)
        return

    await state.update_data(title=model_name, start_price=start_price)
    # delete previous bot message with options if exist
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        f"✅ Вы выбрали: <b>{model_name}</b>\n💰 Стартовая цена: {start_price} тг",
        parse_mode="HTML"
    )

    # ask for photos
    photos_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово ✅", callback_data="photos_done")]
    ])
    await callback.message.answer("\n📸 1. На одной из фоторгафий должен быть IMEI\n"
                                  "2. Должна быть фоторгафия со включенным, желательно белым, экраном\n"
                                  "3. Сфотографируйте устройство со всех сторон\n"
                                  "4. Подробные фото деффектов (если они присутсвуют)\n"
                                  " Когда закончите, нажмите 'Готово ✅'.", reply_markup=photos_kb)
    await callback.answer("1.На одной из фотографий обязательно должен быть номер IMEI !(можете загрузить скриншот из настроек)", show_alert=True)
    await state.set_state(SellerStates.images)



@router.message(SellerStates.images, F.photo)
async def add_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    data = await state.get_data()
    images = data.get("images", [])
    images.append(file_id)
    await state.update_data(images=images)

    photos_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово ✅", callback_data="photos_done")]
    ])

    await message.answer(
        f"📷 Фото добавлено ({len(images)}/5). "
        f"{'Нажмите на Готово ✅ или отправьте ещё фото' if len(images) >= 5 else 'Отправьте ещё фото со всей описанной выше информацией(минимум 5 фото).'}",
        reply_markup=photos_kb
    )


@router.callback_query(F.data == "photos_done")
async def photos_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    images = data.get("images", [])

    if len(images) < 5:
        await callback.answer(
            f"❌ Нужно минимум 5 фото со всеми описанными выше сведениями! Сейчас {len(images)}.",
            show_alert=True
        )
        return

    await callback.message.answer("✍️ Укажите количество памяти:")
    await state.set_state(SellerStates.memory)

@router.message(SellerStates.memory)
async def set_memory(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(memory=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("📅 Укажите год покупки телефона:")
        await state.set_state(SellerStates.year)

@router.message(SellerStates.year)
async def set_year(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(year=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("📦 Опишите общее состояние телефона.\n\n1.Обязательно укажите работают ли микрофоны и динамики.\n\n2.Нет ли проблем с Wi-fi, Bluetooth, звонками или другими модулями?:")
        await state.set_state(SellerStates.condition)

@router.message(SellerStates.condition)
async def set_condition(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(condition=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("🔋 Укажите состояние аккумулятора (в %):")
        await state.set_state(SellerStates.battery)

@router.message(SellerStates.battery)
async def set_battery(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(battery=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("🛠 Был ли телефон в ремонте? Если был то перечислите работы:")
        await state.set_state(SellerStates.repairs)

@router.message(SellerStates.repairs)
async def set_repairs(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(repairs=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("Укажите номер по которому с Вами свяжется победитель:")
        await state.set_state(SellerStates.water)

@router.message(SellerStates.water)
async def set_water(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(water=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("🔒 Нет ли блокировок Apple ID/Google или чего-то еще?:")
        await state.set_state(SellerStates.locks)


# ---------- Get description ----------
@router.message(SellerStates.locks)
async def get_description(message: Message, state: FSMContext):
    await state.update_data(locks=message.text)
    # Показать предпросмотр и опции подтверждения/редактирования
    await show_confirmation(message, state)

# ---------- Show confirmation (preview) ----------
async def show_confirmation(message_or_callback, state: FSMContext):

    data = await state.get_data()

    title = data.get("title")
    start_price = data.get("start_price")
    images = data.get("images", [])
    memory = data.get("memory")
    year = data.get("year")
    condition = data.get("condition")
    battery = data.get("battery")
    repairs = data.get("repairs")
    water = data.get("water")
    locks = data.get("locks")

    # Проверка обязательных данных
    if not title or not start_price or not images or len(images) < 5:
        text = "⚠️ Похоже, какие-то данные лота отсутствуют или фото меньше 5. Пожалуйста, начните заново."
        try:
            if isinstance(message_or_callback, types.CallbackQuery):
                await message_or_callback.message.answer(text, reply_markup=main_menu)
            else:
                await message_or_callback.answer(text, reply_markup=main_menu)
        except Exception:
            logger.exception("show_confirmation: unable to notify user about missing data")
        await state.clear()
        return

    # Формируем предпросмотр
    text = as_marked_section(
        Bold("📋 Предпросмотр лота:"),
        f"📱 Модель: {title}",
        f"💾 Память: {memory}",
        f"📅 Год покупки: {year}",
        f"📦 Состояние: {condition}",
        f"🔋 Батарея: {battery}",
        f"🛠 Ремонты: {repairs}",
        f"📱 Номер телефона: {water}",
        f"🔒 Блокировки: {locks}",
        f"💰 Стартовая цена: {start_price}тг"
    )

    # Клавиатура для публикации или редактирования
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="confirm_publish")],
        [InlineKeyboardButton(text="✏ Изменить память", callback_data="edit_memory")],
        [InlineKeyboardButton(text="✏ Изменить год покупки", callback_data="edit_year")],
        [InlineKeyboardButton(text="✏ Изменить состояние", callback_data="edit_condition")],
        [InlineKeyboardButton(text="✏ Изменить батарею", callback_data="edit_battery")],
        [InlineKeyboardButton(text="✏ Изменить ремонты", callback_data="edit_repairs")],
        [InlineKeyboardButton(text="✏ Изменить номер телефона", callback_data="edit_water")],
        [InlineKeyboardButton(text="✏ Изменить блокировки", callback_data="edit_locks")],
        [InlineKeyboardButton(text="✏ Изменить фото", callback_data="edit_photos")]
    ])

    try:
        if isinstance(message_or_callback, types.CallbackQuery):
            # удаляем старое сообщение-меню, если оно есть
            try:
                await message_or_callback.message.delete()
            except Exception:
                pass
            # отправляем медиа, если есть
            if images:
                try:
                    media = [InputMediaPhoto(media=img) for img in images[:10]]
                    await message_or_callback.message.answer_media_group(media)
                except Exception:
                    logger.exception("Ошибка при отправке media_group в preview")
            await message_or_callback.message.answer(text.as_html(), parse_mode="HTML", reply_markup=kb)
        else:
            if images:
                try:
                    media = [InputMediaPhoto(media=img) for img in images[:10]]
                    await message_or_callback.answer_media_group(media)
                except Exception:
                    logger.exception("Ошибка при отправке media_group в preview (message)")
            await message_or_callback.answer(text.as_html(), parse_mode="HTML", reply_markup=kb)
    except Exception:
        logger.exception("show_confirmation: failed to show preview to user")
        try:
            # fallback simple text
            await (message_or_callback.answer if not isinstance(message_or_callback, types.CallbackQuery) else message_or_callback.message.answer)(
                "Предпросмотр недоступен. Попробуйте снова.", reply_markup=main_menu
            )
        except Exception:
            pass

    # сохраняем, что мы в стадии подтверждения (сохраняем в start_price как legacy state)
    await state.update_data(edit_mode=False)
    await state.set_state(SellerStates.start_price)

# ---------- Edit handlers ----------
# @router.callback_query(F.data == "edit_model")
# async def edit_model(callback: types.CallbackQuery, state: FSMContext):
#     await state.update_data(edit_mode=True)
#     await show_model_keyboard(callback, edit=True)


@router.callback_query(F.data == "edit_photos")
async def edit_photos(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_photos: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True, images=[])
    await callback.message.answer(
        "📸 Отправьте новые фото (минимум 5). Когда закончите, нажмите 'Готово ✅'.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Готово ✅", callback_data="photos_done")]]
        )
    )
    await state.set_state(SellerStates.images)


@router.callback_query(F.data == "edit_memory")
async def edit_memory(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_memory: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("✍️ Укажите количество памяти:")
    await state.set_state(SellerStates.memory)


@router.callback_query(F.data == "edit_year")
async def edit_year(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_year: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("📅 Укажите год покупки телефона:")
    await state.set_state(SellerStates.year)


@router.callback_query(F.data == "edit_condition")
async def edit_condition(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_condition: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("📦 Опишите общее состояние телефона:")
    await state.set_state(SellerStates.condition)


@router.callback_query(F.data == "edit_battery")
async def edit_battery(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_battery: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("🔋 Укажите состояние аккумулятора:")
    await state.set_state(SellerStates.battery)


@router.callback_query(F.data == "edit_repairs")
async def edit_repairs(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_repairs: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("🛠 Был ли телефон в ремонте? (Да/Нет):")
    await state.set_state(SellerStates.repairs)


@router.callback_query(F.data == "edit_water")
async def edit_water(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_water: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("Введите номер телефона:")
    await state.set_state(SellerStates.water)


@router.callback_query(F.data == "edit_locks")
async def edit_locks(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data:
        # данные утеряны — предупреждаем
        logger.warning("edit_locks: no state data for user %s", callback.from_user.id)
        await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.",
                                      reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(edit_mode=True)
    await callback.message.answer("🔒 Нет ли блокировок Apple ID/Google? (Да/Нет):")
    await state.set_state(SellerStates.locks)









# ---------- Confirm publish ----------
@router.callback_query(F.data == "confirm_publish")
async def confirm_publish(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Полный список обязательных полей
    required_fields = [
        "title", "start_price", "images",
        "memory", "year", "condition", "battery",
        "repairs", "water", "locks"
    ]

    # Проверка заполненности
    missing = [f for f in required_fields if not data.get(f)]
    if missing or len(data.get("images", [])) < 5:
        logger.warning("confirm_publish: missing data for user %s: %s", callback.from_user.id, missing)
        try:
            await callback.message.answer(
                "❌ Лот устарел, неполный или фото меньше 5. Пожалуйста, начните создание заново.",
                reply_markup=main_menu
            )
        except Exception:
            try:
                await callback.answer("❌ Лот устарел или неполный.", show_alert=True)
            except Exception:
                pass
        await state.clear()
        return

    title = data["title"]
    start_price = data["start_price"]
    images = data["images"]

    # Формируем детальное описание
    full_description = (
        f"💾 Память: {data['memory']}\n"
        f"📅 Год покупки: {data['year']}\n"
        f"📦 Состояние: {data['condition']}\n"
        f"🔋 Аккумулятор: {data['battery']}\n"
        f"🛠 Ремонт: {data['repairs']}\n"
        f"Номер телефона: {data['water']}\n"
        f"🔒 Блокировки: {data['locks']}"
    )

    try:
        async with async_session() as session:
            lot = Lot(
                title=data["title"],
                description="",  # описание формируем потом
                start_price=data["start_price"],
                seller_id=callback.from_user.id,
                memory=data["memory"],
                year=data["year"],
                condition=data["condition"],
                battery=data["battery"],
                repairs=data["repairs"],
                water=data["water"],
                locks=data["locks"],
                status="pending"
            )
            session.add(lot)
            await session.flush()

            for file_id in images:
                session.add(LotImage(lot_id=lot.id, file_id=file_id))

            await session.commit()

            # уведомляем продавца
        await callback.message.answer("⌛ Ваш лот отправлен на модерацию. Ожидайте решения.", reply_markup=main_menu)

        # Сообщение в канал
        text = as_marked_section(
            Bold("🔥 Новый лот!"),
            f"📱 {title}",
            full_description,
            f"💰 Старт: {start_price}тг",
            f"👤 Продавец: {callback.from_user.id}"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{lot.id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{lot.id}")]
        ])

        if images:
            try:
                media = [InputMediaPhoto(media=img) for img in images[:10]]
                await callback.bot.send_media_group(chat_id=settings.moderator_chat_id, media=media)
            except Exception:
                logger.exception("confirm_publish: failed to send media_group to moder channel")


        await callback.bot.send_message(settings.moderator_chat_id, text.as_html(), reply_markup=kb)
    except Exception:
        logger.exception("confirm_publish: failed to send message to moder channel")
        await callback.message.answer("❌ Ошибка при сохранении лота. Попробуйте позже.", reply_markup=main_menu)
    finally:
        await state.clear()

@router.callback_query(F.data.startswith("approve_"))
async def approve_lot(callback: types.CallbackQuery):
    lot_id = int(callback.data.split("_")[1])
    async with async_session() as session:
        result = await session.execute(
            select(Lot).options(selectinload(Lot.images)).where(Lot.id == lot_id)
        )
        lot = result.scalar_one_or_none()
        logger.info("Approve pressed for lot_id=%s", lot_id)
        if not lot or lot.status != LotStatus.pending:
            await callback.answer("⚠️ Лот не найден или уже обработан.", show_alert=True)
            return
        lot.status = LotStatus.approved
        await session.commit()

        images = [img.file_id for img in lot.images][:10]

    full_description = (
        f"💾 Память: {lot.memory}\n"
        f"📅 Год покупки: {lot.year}\n"
        f"📦 Состояние: {lot.condition}\n"
        f"🔋 Аккумулятор: {lot.battery}\n"
        f"🛠 Ремонт: {lot.repairs}\n"
        f"🔒 Блокировки: {lot.locks}\n"
        f"ID: {lot.id}"
    )

    text = as_marked_section(
        Bold("🔥 Новый лот!"),
        f"📱 {lot.title}",
        full_description,
        f"💰 Старт: {lot.start_price}тг",
        f"⏳ Торги начнутся через {settings.auction_duration_minutes} минут."
    )


    if images:
        media = [InputMediaPhoto(media=img) for img in images]
        await callback.bot.send_media_group(chat_id=settings.auction_channel_id, media=media)

    await callback.bot.send_message(settings.auction_channel_id, text.as_html())

    # старт аукциона
    asyncio.create_task(start_auction(lot.id, callback.bot))
    bot = callback.bot
    await bot.send_message(lot.seller_id, f"✅ Лот одобрен и опубликован! Торги начнутся через {settings.auction_duration_minutes} минут")
    await callback.answer(f"✅ Лот одобрен и опубликован! Торги начнутся через {settings.auction_duration_minutes} минут", show_alert=True)




@router.message(F.text == "ℹ️ Правила")
async def rules_handler(message: Message):
    await message.answer(
        "ℹ️ Аукцион — это быстрый способ продать телефон.\n\n"
        "1. Выберите модель 📱\n"
        "2. Загрузите фото 📸\n"
        "3. Опишите товар 📝\n\n"
        "❗ После публикации изменить лот будет нельзя!",
        reply_markup=main_menu
    )
    #file = FSInputFile(r"handlers\public_offer_full.pdf")
    #await message.answer_document(file, caption="Вот ваша публичная оферта 📄")
    await message.answer_document("BQACAgIAAxkBAAIMMmiurZ79j_kRakOnl_FCaeLh3h6WAAIzeAACa6h5SWwb6wGFMuMeNgQ", caption="Вот ваша публичная оферта 📄")  # file_id



# --- хэндлер согласия продавца ---
@router.callback_query(F.data.startswith("accept_deal_"))
async def accept_deal(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    lot_id, winner_id = int(parts[-2]), int(parts[-1])

    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot:
            await callback.answer("⚠️ Лот не найден.", show_alert=True)
            return
        lot_title = lot.title
        seller_contact = lot.water  # используем как номер телефона продавца

    # Редактируем сообщение: убираем кнопки и меняем текст
    await callback.message.edit_text(
        f"✅ Вы приняли сделку по лоту '{lot_title}'. Контакт передан победителю."
    )
    await callback.bot.send_message(settings.moderator_chat_id, f"{lot_title}:Контакт {seller_contact} передан победителю {winner_id}.")

    # Сообщение победителю
    await callback.bot.send_message(
        int(winner_id),
        f"✅ Продавец принял вашу ставку по лоту '{lot_title}'.\n"
        f"Связаться можно по номеру: {seller_contact}"
    )

    await callback.answer()


@router.callback_query(F.data.startswith("reject_deal_"))
async def reject_deal(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    lot_id, winner_id = int(parts[-2]), int(parts[-1])

    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot:
            await callback.answer("⚠️ Лот не найден.", show_alert=True)
            return
        lot_title = lot.title

    # Редактируем сообщение: убираем кнопки и меняем текст
    await callback.message.edit_text(
        f"❌ Вы отказались от сделки по лоту '{lot_title}'."
    )

    # Сообщение победителю
    await callback.bot.send_message(
        int(winner_id),
        f"❌ К сожалению, продавец не принял вашу ставку по лоту '{lot_title}'."
    )

    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject_lot(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    # проверяем, что это именно reject_<lot_id>, а не reject_deal_...
    if len(parts) != 2:
        return  # игнорируем reject_deal
    lot_id = int(parts[1])

    async with async_session() as session:
        lot = await session.get(Lot, lot_id)
        if not lot or lot.status != LotStatus.pending:
            await callback.answer("⚠️ Лот не найден или уже обработан.", show_alert=True)
            return

        lot.status = LotStatus.rejected
        await session.commit()

    bot = callback.bot
    await bot.send_message(lot.seller_id,"❌Ваш лот отклонён.Пожалуйста, уточните причину у службы поддержки")
    await callback.answer("❌ Лот отклонён", show_alert=True)






# @router.message(
#         F.content_type.in_({"document", "photo", "video", "audio", "voice", "sticker", "video_note", "animation"}))
# async def any_file_handler(message: Message):
#         file_obj = None
#         kind = None
#
#         if message.document:
#             file_obj = message.document
#             kind = "document"
#         elif message.photo:
#             file_obj = message.photo[-1]  # берём самое большое фото
#             kind = "photo"
#         elif message.video:
#             file_obj = message.video
#             kind = "video"
#         elif message.audio:
#             file_obj = message.audio
#             kind = "audio"
#         elif message.voice:
#             file_obj = message.voice
#             kind = "voice"
#         elif message.sticker:
#             file_obj = message.sticker
#             kind = "sticker"
#         elif message.video_note:
#             file_obj = message.video_note
#             kind = "video_note"
#         elif message.animation:
#             file_obj = message.animation
#             kind = "animation"
#
#         if not file_obj:
#             return await message.answer("Файл не распознан")
#
#         await message.answer(
#             f"Тип: <b>{kind}</b>\n"
#             f"file_id:\n<code>{file_obj.file_id}</code>\n\n"
#             f"file_unique_id:\n<code>{file_obj.file_unique_id}</code>",
#             parse_mode="HTML"
#         )



