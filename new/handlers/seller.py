from aiogram import Router, F, types
from aiogram.types import Message, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, \
    KeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.utils.formatting import as_marked_section, Bold
import asyncio
import logging


from new.database import async_session
from new.models import Lot, LotImage, LotStatus
from new.states import SellerStates
from new.config import settings
from new.auctions.logic import start_auction

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
    "iPhone 13": 30000,
    "iPhone 14": 40000,
    "iPhone 15 Pro": 60000,
    "Samsung S21": 28000,
    "Samsung S24 Ultra": 50000,
}

# reply keyboard (fallback / главное меню)
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📤 Хочу продать"), KeyboardButton(text="📋 Список аукционов")],
        [KeyboardButton(text="ℹ️ Правила"), KeyboardButton(text="📞 Поддержка")]
    ],
    resize_keyboard=True
)

# main_menu_inline = InlineKeyboardMarkup(
#     inline_keyboard=[
#         [InlineKeyboardButton(text="📤 Хочу продать", callback_data="start_sell")],
#         [InlineKeyboardButton(text="📋 Список аукционов", callback_data="list_auctions")],
#         [InlineKeyboardButton(text="ℹ️ Правила", callback_data="rules")],
#         [InlineKeyboardButton(text="📞 Поддержка", url="https://t.me/username_support")]
#     ]
# )
#
# @router.callback_query(F.data == "start_sell")
# async def alert_info(callback: types.CallbackQuery, state: FSMContext):
#     # Покажем алерт с краткой информацией
#     await callback.answer(
#         "ℹ️ Аукцион — это способ быстро и выгодно продать ваш телефон. "
#         "Лоты публикуются в канале, и дилеры делают ставки.\n\n"
#         "⏳ Торги длятся ограниченное время, после чего победитель получает ваш контакт.",
#         show_alert=True
#     )
#     # Переход к выбору модели
#     await show_model_keyboard(callback)
#     await state.set_state(SellerStates.title)
#

# ---------- Start selling ----------
@router.message(Command("sell"))
@router.message(F.text == "📤 Хочу продать")
async def start_selling(message: Message, state: FSMContext):
    await message.answer(

        "ℹ️ Аукцион — это быстрый способ выгодно продать телефон.\n\n\n"
        "📱 УСЛОВИЯ ДЛЯ ПРОДАВЦА"
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
        f"✅ Вы выбрали: <b>{model_name}</b>\n💰 Стартовая цена: {start_price}₽",
        parse_mode="HTML"
    )

    # ask for photos
    photos_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Готово ✅", callback_data="photos_done")]
    ])
    await callback.message.answer("📸 1. На одной из фоторгафий должен быть IMEI\n"
                                  "2. Должна быть фоторгафия со включенным, желательно белым, экраном\n"
                                  "3. Сфотографируйте устройство со всех сторон\n"
                                  "4. Подробные фото деффектов (если они присутсвуют)\n"
                                  " Когда закончите, нажмите 'Готово ✅'.", reply_markup=photos_kb)
    await callback.answer("1.На одной из фотографий обязательно должен быть номер IMEI !(можете загрузить скриншот из настроек)", show_alert=True)
    await state.set_state(SellerStates.images)

# ---------- Add photo ----------
# @router.message(SellerStates.images, F.photo)
# async def add_photo(message: Message, state: FSMContext):
#     file_id = message.photo[-1].file_id
#     data = await state.get_data()
#     images = data.get("images", [])
#     images.append(file_id)
#     await state.update_data(images=images)
#     photos_kb = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="Готово ✅", callback_data="photos_done")]
#     ])
#     await message.answer("📷 Фото добавлено. Нажмите на Готово ✅ или отправьте еще фото", reply_markup=photos_kb)
#
# # ---------- Photos done ----------
# @router.callback_query(F.data == "photos_done")
# async def photos_done(callback: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     if not data.get("images"):
#         await callback.answer("❌ Добавьте хотя бы одно фото!", show_alert=True)
#         return
#     await callback.message.answer("✍️ Введите подробное описание устройства:")
#     await state.set_state(SellerStates.description)

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
        await message.answer("📦 Опишите общее состояние телефона:")
        await state.set_state(SellerStates.condition)

@router.message(SellerStates.condition)
async def set_condition(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(condition=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("🔋 Укажите состояние аккумулятора (в % или словах):")
        await state.set_state(SellerStates.battery)

@router.message(SellerStates.battery)
async def set_battery(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(battery=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("🛠 Был ли телефон в ремонте? (Да/Нет):")
        await state.set_state(SellerStates.repairs)

@router.message(SellerStates.repairs)
async def set_repairs(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(repairs=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("💧 Падал ли в воду? (Да/Нет):")
        await state.set_state(SellerStates.water)

@router.message(SellerStates.water)
async def set_water(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(water=message.text)
    if data.get("edit_mode"):
        await return_to_preview(message, state)
    else:
        await message.answer("🔒 Нет ли блокировок Apple ID/Google? (Да/Нет):")
        await state.set_state(SellerStates.locks)


# ---------- Get description ----------
@router.message(SellerStates.locks)
async def get_description(message: Message, state: FSMContext):
    await state.update_data(locks=message.text)
    # Показать предпросмотр и опции подтверждения/редактирования
    await show_confirmation(message, state)

# ---------- Show confirmation (preview) ----------
async def show_confirmation(message_or_callback, state: FSMContext):
    # data = await state.get_data()
    #
    # # Defensive read — don't assume keys exist
    # title = data.get("title")
    # description = data.get("description")
    # start_price = data.get("start_price")
    # images = data.get("images", [])
    #
    # # Если каких-то обязательных данных нет — предупредим пользователя
    # if not title or not description or not start_price:
    #     # данные потеряны — попросим начать заново
    #     text = "⚠️ Похоже, какие-то данные лота отсутствуют. Пожалуйста, начните создание лота заново."
    #     try:
    #         if isinstance(message_or_callback, types.CallbackQuery):
    #             await message_or_callback.message.answer(text, reply_markup=main_menu)
    #         else:
    #             await message_or_callback.answer(text, reply_markup=main_menu)
    #     except Exception:
    #         logger.exception("show_confirmation: unable to notify user about missing data")
    #     await state.clear()
    #     return
    #
    # text = as_marked_section(
    #     Bold("Предпросмотр лота:"),
    #     f"📱 Модель: {title}",
    #     f"📝 Описание: {description}",
    #     f"💰 Стартовая цена: {start_price}₽"
    # )
    #
    # kb = InlineKeyboardMarkup(inline_keyboard=[
    #     [InlineKeyboardButton(text="✅ Опубликовать", callback_data="confirm_publish")],
    #     [InlineKeyboardButton(text="✏ Изменить модель", callback_data="edit_model")],
    #     [InlineKeyboardButton(text="✏ Изменить описание", callback_data="edit_description")],
    #     [InlineKeyboardButton(text="✏ Изменить фото", callback_data="edit_photos")]
    # ])
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
        f"💧 Попадание в воду: {water}",
        f"🔒 Блокировки: {locks}",
        f"💰 Стартовая цена: {start_price}₽"
    )

    # Клавиатура для публикации или редактирования
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="confirm_publish")],
        [InlineKeyboardButton(text="✏ Изменить память", callback_data="edit_memory")],
        [InlineKeyboardButton(text="✏ Изменить год покупки", callback_data="edit_year")],
        [InlineKeyboardButton(text="✏ Изменить состояние", callback_data="edit_condition")],
        [InlineKeyboardButton(text="✏ Изменить батарею", callback_data="edit_battery")],
        [InlineKeyboardButton(text="✏ Изменить ремонты", callback_data="edit_repairs")],
        [InlineKeyboardButton(text="✏ Изменить попадание в воду", callback_data="edit_water")],
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
    await callback.message.answer("💧 Падал ли в воду? (Да/Нет):")
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







# @router.callback_query(F.data == "edit_model")
# async def edit_model(callback: types.CallbackQuery, state: FSMContext):
#     # Вернуться к выбору модели
#     await show_model_keyboard(callback, edit=True)
#     await state.set_state(SellerStates.title)
#
# @router.callback_query(F.data == "edit_description")
# async def edit_description(callback: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     if not data:
#         # данные утеряны — предупреждаем
#         logger.warning("edit_description: no state data for user %s", callback.from_user.id)
#         await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.", reply_markup=main_menu)
#         await state.clear()
#         return
#     await callback.message.answer("✍️ Введите новое описание:")
#     await state.set_state(SellerStates.description)
#
# @router.callback_query(F.data == "edit_photos")
# async def edit_photos(callback: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()
#     if not data:
#         logger.warning("edit_photos: no state data for user %s", callback.from_user.id)
#         await callback.message.answer("❌ Данные лота утеряны. Пожалуйста, начните создание заново.", reply_markup=main_menu)
#         await state.clear()
#         return
#     # сбросим фото и попросим загрузить заново
#     await state.update_data(images=[])
#     photos_kb = InlineKeyboardMarkup(inline_keyboard=[
#         [InlineKeyboardButton(text="Готово ✅", callback_data="photos_done")]
#     ])
#     await callback.message.answer("📸 Отправьте новые фото. Когда закончите, нажмите 'Готово ✅'.", reply_markup=photos_kb)
#     await state.set_state(SellerStates.images)

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
        f"💧 Падал в воду: {data['water']}\n"
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
            f"💰 Старт: {start_price}₽",
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
        f"💧 Падал в воду: {lot.water}\n"
        f"🔒 Блокировки: {lot.locks}"
    )

    text = as_marked_section(
        Bold("🔥 Новый лот!"),
        f"📱 {lot.title}",
        full_description,
        f"💰 Старт: {lot.start_price}₽",
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

@router.callback_query(F.data.startswith("reject_"))
async def reject_lot(callback: types.CallbackQuery):
    lot_id = int(callback.data.split("_")[1])

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
# @router.callback_query(F.data == "confirm_publish")
# async def confirm_publish(callback: types.CallbackQuery, state: FSMContext):
#     data = await state.get_data()

#
#     # валидируем наличие обязательных полей
#     required = ["title", "description", "start_price"]
#     if not all(k in data and data[k] for k in required):
#         logger.warning("confirm_publish: missing data for user %s: %s", callback.from_user.id, data)
#         try:
#             await callback.message.answer("❌ Лот устарел или данные утеряны. Пожалуйста, начните создание заново.", reply_markup=main_menu)
#         except Exception:
#             try:
#                 await callback.answer("❌ Лот устарел или данные утеряны.", show_alert=True)
#             except Exception:
#                 pass
#         await state.clear()
#         return
#
#     title = data["title"]
#     description = data["description"]
#     start_price = data["start_price"]
#     images = data.get("images", [])
#
#     try:
#         async with async_session() as session:
#             lot = Lot(
#                 title=title,
#                 description=description,
#                 start_price=start_price,
#                 seller_id=callback.from_user.id,
#             )
#             session.add(lot)
#             await session.flush()
#
#             for file_id in images:
#                 session.add(LotImage(lot_id=lot.id, file_id=file_id))
#
#             await session.commit()
#
#         # подготовим текст и медиа и отправим в канал
#         text = as_marked_section(
#             Bold("🔥 Новый лот!"),
#             f"📱 {title}",
#             f"📝 {description}",
#             f"💰 Старт: {start_price}₽",
#             f"⏳ Торги начнутся через {settings.auction_duration_minutes} минут."
#         )
#
#         if images:
#             try:
#                 media = [InputMediaPhoto(media=img) for img in images[:10]]
#                 await callback.bot.send_media_group(chat_id=settings.auction_channel_id, media=media)
#             except Exception:
#                 logger.exception("confirm_publish: failed to send media_group to channel")
#
#         try:
#             await callback.bot.send_message(settings.auction_channel_id, text.as_html())
#         except Exception:
#             logger.exception("confirm_publish: failed to send message to channel")
#
#         # запуск аукциона
#         try:
#             asyncio.create_task(start_auction(lot.id, callback.bot))
#         except Exception:
#             logger.exception("confirm_publish: failed to start auction task")
#
#         try:
#             await callback.message.answer("✅ Лот опубликован! Торги начнутся через {} минут.".format(settings.auction_duration_minutes), reply_markup=main_menu)
#         except Exception:
#             try:
#                 await callback.answer("✅ Лот опубликован!", show_alert=True)
#             except Exception:
#                 pass
#
#     except Exception:
#         logger.exception("confirm_publish: unexpected error while saving/publishing lot for user %s", callback.from_user.id)
#         try:
#             await callback.message.answer("❌ Не удалось опубликовать лот. Попробуйте позже.", reply_markup=main_menu)
#         except Exception:
#             try:
#                 await callback.answer("❌ Не удалось опубликовать лот.", show_alert=True)
#             except Exception:
#                 pass
#     finally:
#         await state.clear()

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
    file = FSInputFile(r"C:\Users\kachu\Downloads\public_offer_full.pdf")
    await message.answer_document(file, caption="Вот ваша публичная оферта 📄")



#oooooooooooooooooooooooo
# import asyncio
# import re
# from io import BytesIO
# from PIL import Image, ImageStat
# import pytesseract
# from aiogram import Bot, Dispatcher, F, Router
# from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import StatesGroup, State
# from aiogram.filters import CommandStart
#
# MODEL_PRICES = {
#     "iPhone 12": 85000,
#     "iPhone 12 Pro": 120000,
#     "iPhone 13": 150000,
#     "iPhone 13 Pro": 180000,
#     "Samsung Galaxy S21": 90000,
#     "Samsung Galaxy S22": 130000
# }
#
# def models_kb():
#     return ReplyKeyboardMarkup(
#         keyboard=[[KeyboardButton(text=m)] for m in MODEL_PRICES],
#         resize_keyboard=True
#     )
#
# def finish_photos_kb():
#     return ReplyKeyboardMarkup(
#         keyboard=[
#             [KeyboardButton(text="✅ Достаточно фото")],
#         ],
#         resize_keyboard=True
#     )
#
# # ==== Проверки фото ====
# def is_unique_photo(file_bytes: bytes, existing_hashes: set) -> bool:
#     # import hashlib
#     # photo_hash = hashlib.md5(file_bytes).hexdigest()
#     # if photo_hash in existing_hashes:
#     #     return False
#     # existing_hashes.add(photo_hash)
#     return True
#
# def is_good_quality(image: Image.Image, min_width=400, min_height=400, min_brightness=30) -> bool:
#     # if image.width < min_width or image.height < min_height:
#     #     return False
#     # stat = ImageStat.Stat(image.convert("L"))
#     # brightness = stat.mean[0]
#     # if brightness < min_brightness:
#     #     return False
#     return True
#
# def extract_imei_from_image(image: Image.Image) -> str | None:
#     text = pytesseract.image_to_string(image)
#     matches = re.findall(r"\b\d{15}\b", text)
#     return matches[0] if matches else None
#
# # ==== Обработчики ====
# @router.message(CommandStart())
# async def cmd_start(message: Message):
#     await message.answer("👋 Привет! Готов продать свой телефон за 30 минут без лишних контактов?", reply_markup=main_menu())
#
# @router.message(F.text == "📤 Хочу продать")
# async def choose_model(message: Message, state: FSMContext):
#     await message.answer("📱 Выберите модель телефона:", reply_markup=models_kb())
#     await state.set_state(SellerStates.model)
#
# @router.message(SellerStates.model)
# async def set_model(message: Message, state: FSMContext):
#     model = message.text
#     if model not in MODEL_PRICES:
#         await message.answer("❌ Пожалуйста, выберите модель из списка.", reply_markup=models_kb())
#         return
#     start_price = MODEL_PRICES[model]
#     await state.update_data(model=model, price=start_price, photos=[], photo_hashes=set())
#     await message.answer(f"✅ Модель: {model}\n💰 Стартовая цена: {start_price} ₸\n\nТеперь пришлите фото телефона (минимум 3).", reply_markup=finish_photos_kb())
#     await state.set_state(SellerStates.photos)
#
# @router.message(SellerStates.photos, F.photo)
# async def collect_photos(message: Message, state: FSMContext):
#     data = await state.get_data()
#     photos = data.get("photos", [])
#     photo_hashes = data.get("photo_hashes", set())
#
#     file = await message.bot.get_file(message.photo[-1].file_id)
#     file_bytes = await message.bot.download_file(file.file_path)
#     file_bytes_data = file_bytes.read()
#
#     img = Image.open(BytesIO(file_bytes_data))
#
#     if not is_unique_photo(file_bytes_data, photo_hashes):
#         await message.answer("⚠ Это фото уже было отправлено. Пришлите другое.")
#         return
#     if not is_good_quality(img):
#         await message.answer("⚠ Фото слишком маленькое или темное. Пришлите более качественное.")
#         return
#
#     photos.append(message.photo[-1].file_id)
#     await state.update_data(photos=photos, photo_hashes=photo_hashes)
#
#     await message.answer(f"📸 Фото {len(photos)} получено. Нужно минимум 3.")
#
# @router.message(SellerStates.photos, F.text == "✅ Достаточно фото")
# async def enough_photos(message: Message, state: FSMContext):
#     data = await state.get_data()
#     if len(data.get("photos", [])) < 3:
#         await message.answer("❌ Нужно минимум 3 фото.")
#         return
#     await message.answer("📷 Теперь пришлите фото экрана с IMEI.")
#     await state.set_state(SellerStates.imei)
#
# @router.message(SellerStates.imei, F.photo)
# async def handle_imei_photo(message: Message, state: FSMContext):
#     file = await message.bot.get_file(message.photo[-1].file_id)
#     file_bytes = await message.bot.download_file(file.file_path)
#     img = Image.open(BytesIO(file_bytes.read()))
#     imei = 444444444
#     # imei = extract_imei_from_image(img)
#     # if not imei:
#     #     await message.answer("❌ Не удалось распознать IMEI. Введите его вручную.")
#     #     return
#     await state.update_data(imei=imei)
#     await message.answer(f"✅ IMEI получен: {imei}\n\nУкажите объём памяти (например: 128GB).")
#     await state.set_state(SellerStates.memory)
#
# @router.message(SellerStates.memory)
# async def set_memory(message: Message, state: FSMContext):
#     await state.update_data(memory=message.text)
#     await message.answer("📅 Укажите год покупки телефона:")
#     await state.set_state(SellerStates.year)
#
# @router.message(SellerStates.year)
# async def set_year(message: Message, state: FSMContext):
#     await state.update_data(year=message.text)
#     await message.answer("📦 Опишите общее состояние телефона:")
#     await state.set_state(SellerStates.condition)
#
# @router.message(SellerStates.condition)
# async def set_condition(message: Message, state: FSMContext):
#     await state.update_data(condition=message.text)
#     await message.answer("🔋 Укажите состояние аккумулятора (в % или словах):")
#     await state.set_state(SellerStates.battery)
#
# @router.message(SellerStates.battery)
# async def set_battery(message: Message, state: FSMContext):
#     await state.update_data(battery=message.text)
#     await message.answer("🛠 Был ли телефон в ремонте? (Да/Нет):")
#     await state.set_state(SellerStates.repairs)
#
# @router.message(SellerStates.repairs)
# async def set_repairs(message: Message, state: FSMContext):
#     await state.update_data(repairs=message.text)
#     await message.answer("💧 Падал ли в воду? (Да/Нет):")
#     await state.set_state(SellerStates.water)
#
# @router.message(SellerStates.water)
# async def set_water(message: Message, state: FSMContext):
#     await state.update_data(water=message.text)
#     await message.answer("🔒 Нет ли блокировок Apple ID/Google? (Да/Нет):")
#     await state.set_state(SellerStates.locks)
#
# @router.message(SellerStates.locks)
# async def set_locks(message: Message, state: FSMContext):
#     await state.update_data(locks=message.text)
#     data = await state.get_data()
#
#     lot_summary = (
#         f"📱 Модель: {data['model']}\n"
#         f"💰 Стартовая цена: {data['price']} ₸\n"
#         f"🆔 IMEI: {data['imei']}\n"
#         f"💾 Память: {data['memory']}\n"
#         f"📅 Год: {data['year']}\n"
#         f"📦 Состояние: {data['condition']}\n"
#         f"🔋 Аккумулятор: {data['battery']}\n"
#         f"🛠 Ремонт: {data['repairs']}\n"
#         f"💧 Вода: {data['water']}\n"
#         f"🔒 Блокировки: {data['locks']}\n"
#         f"📷 Фото: {len(data['photos'])} шт."
#     )
#
#     await message.answer("✅ Ваша заявка:\n\n" + lot_summary + "\n\nОтправляем на модерацию...")
#     await state.clear()
