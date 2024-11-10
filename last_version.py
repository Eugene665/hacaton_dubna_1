import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler
import sqlite3
import os
from PIL import Image
import torch
from torchvision import models, transforms
from torchvision.models import ResNet50_Weights

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация модели и устройства
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = models.resnet50(weights=ResNet50_Weights.IMAGENET1K_V1).to(device)
model.eval()

# Шаги диалога
CHOOSE_ACTION, ADD_PHOTO, ADD_DATA, CONFIRMATION, SHOW_ADS, LIKE_AD, NEXT_AD, CONFIRM_CONTINUE = range(8)

TOKEN = "7704971887:AAGz0lHUYyv0BsLJdnV9sS50vCQgh2bM9G8"

async def start(update: Update, context: CallbackContext) -> int:
    logger.info("Команда /start получена от %s", update.message.from_user.username)
    await update.message.reply_text('Добро пожаловать!')
    return await main_menu(update, context)

async def main_menu(update: Update, context: CallbackContext) -> int:
    logger.info("Отображение главного меню")
    keyboard = [
        [KeyboardButton("Я хочу найти"), KeyboardButton("Я хочу помочь найти")],
        [KeyboardButton("Отмена")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return CHOOSE_ACTION

# Обработка текстовых сообщений не по теме
async def handle_unrelated_message(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Извините, я не понимаю это сообщение. Пожалуйста, попробуйте выбрать действие из меню, нажать кнопку 'Отмена' или отправьте команду /start для начала. Что-то из этого Вам точно поможет!")

async def choose_action(update: Update, context: CallbackContext) -> int:
    user_choice = update.message.text
    logger.info("Выбор пользователя: %s", user_choice)

    if user_choice == "Отмена":
        await update.message.reply_text("Вы отменили текущую операцию.")
        return await main_menu(update, context)
    elif user_choice == "Я хочу помочь найти":
        context.user_data['is_searching'] = True
        await update.message.reply_text("Запрос фото.")
        return ADD_PHOTO
    elif user_choice == "Я хочу найти":
        logger.info("Переход к отображению объявлений")
        await show_ads(update, context)
        return ADD_PHOTO
    else:
        logger.warning("Неизвестный выбор: %s", user_choice)
        return await main_menu(update, context)


async def show_ads(update: Update, context: CallbackContext) -> int:
    logger.info("Показ объявлений начат")
    conn = sqlite3.connect("animals.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, photo_path, nickname, location, breed, color, features, description, user_contact FROM animals WHERE status = ?",
        ("найдена на улице",))
    ads = cursor.fetchall()
    conn.close()

    if not ads:
        await update.message.reply_text("Пока здесь нет объявлений.")
        logger.info("Объявлений нет.")
        return ConversationHandler.END

    context.user_data['ads'] = ads
    context.user_data['current_ad_index'] = 0
    await display_current_ad(update, context)
    return SHOW_ADS

async def display_current_ad(update: Update, context: CallbackContext) -> None:
    ads = context.user_data['ads']
    index = context.user_data['current_ad_index']
    ad = ads[index]

    ad_text = f"Кличка: {ad[2]}\nМесто: {ad[3]}\nПорода: {ad[4]}\nОкраска: {ad[5]}\nПриметы: {ad[6]}\nОписание: {ad[7]}\n"

    # Кнопки: Лайк, Следующее объявление по горизонтали и Отмена внизу
    buttons = [
        [InlineKeyboardButton("Лайк", callback_data="like"),
         InlineKeyboardButton("Следующее объявление", callback_data="next_ad")],
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Обрабатываем если это callback_query (т.е. кнопка была нажата)
    if update.callback_query:
        query = update.callback_query
        if ad[1]:
            await query.message.reply_photo(photo=open(ad[1], 'rb'), caption=ad_text, reply_markup=reply_markup)
        else:
            await query.message.reply_text(ad_text, reply_markup=reply_markup)
    else:
        # Если это обычное сообщение, используем update.message
        if ad[1]:
            await update.message.reply_photo(photo=open(ad[1], 'rb'), caption=ad_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(ad_text, reply_markup=reply_markup)

    logger.info("Отображено объявление %s", ad)


async def like_ad(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    # Получаем индекс текущего объявления
    index = context.user_data['current_ad_index']
    ad = context.user_data['ads'][index]
    logger.info("Лайк поставлен на объявление %s", ad[0])

    # Формируем текст с информацией о пользователе
    ad_text = f"Контактный юзернейм автора: @{ad[8]}\n"

    # Кнопки: Следующее объявление и Отмена
    buttons = [
        [InlineKeyboardButton("Следующее объявление", callback_data="next_ad")],
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Проверяем, есть ли фото в объявлении
    if ad[1]:
        # Если есть фото, редактируем только текст, не фото
        try:
            await query.edit_message_caption(caption=ad_text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error("Ошибка при редактировании фото: %s", e)
    else:
        # Если нет фото, редактируем только текст
        try:
            await query.edit_message_text(text=ad_text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error("Ошибка при редактировании текста: %s", e)

    return CONFIRM_CONTINUE


async def next_ad(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    logger.info("Запрос следующего объявления")

    context.user_data['current_ad_index'] += 1
    if context.user_data['current_ad_index'] >= len(context.user_data['ads']):
        # Проверяем, является ли сообщение, которое нужно отредактировать, текстом или фото
        if query.message.text:
            await query.edit_message_text("Объявления закончились.")
        else:
            # Если это не текст, редактируем caption (если это фото)
            await query.edit_message_caption("Объявления закончились.")
        logger.info("Объявления закончились.")
        return ConversationHandler.END

    await display_current_ad(update, context)
    return SHOW_ADS


async def cancel(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()  # Подтверждаем, что запрос обработан

    # Теперь используем update.callback_query.message вместо update.message
    await query.message.reply_text("Выберите действие:", reply_markup=ReplyKeyboardMarkup(
        [
            [KeyboardButton("Я хочу найти"), KeyboardButton("Я хочу помочь найти")],
            [KeyboardButton("Отмена")]
        ],
        one_time_keyboard=True,
        resize_keyboard=True
    ))

    return CHOOSE_ACTION  # Возвращаем состояние главного меню


# Обработка добавления фото
async def add_photo(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()  # Очистка данных для новой анкеты

    if update.message.text == "Отмена":
        await update.message.reply_text("Добавление отменено.")
        return await main_menu(update, context)

    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото, или нажмите Отмена для возврата.")
        return ADD_PHOTO

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    photo_path = os.path.join("photos", f"{photo.file_id}.jpg")
    await photo_file.download_to_drive(photo_path)
    context.user_data['photo_path'] = photo_path

    await update.message.reply_text("Введите кличку кошки/собаки, если знаете:")
    return ADD_DATA


# Поочередно собираем дополнительные данные
async def add_data(update: Update, context: CallbackContext) -> int:
    # Проверяем, если пользователь выбрал отмену
    if update.message.text == "Отмена":
        await update.message.reply_text("Добавление отменено.")
        return await main_menu(update, context)

    # Последовательно запрашиваем каждое поле
    if 'nickname' not in context.user_data:
        context.user_data['nickname'] = update.message.text
        await update.message.reply_text("Введите место нахождения(город, район):")
        return ADD_DATA

    elif 'location' not in context.user_data:
        context.user_data['location'] = update.message.text
        await update.message.reply_text("Введите породу кошки/собаки:")
        return ADD_DATA

    elif 'breed' not in context.user_data:
        context.user_data['breed'] = update.message.text
        await update.message.reply_text("Введите окраску:")
        return ADD_DATA

    elif 'color' not in context.user_data:
        context.user_data['color'] = update.message.text
        await update.message.reply_text("Введите описание кошки/собаки, места где Вы её видели:")
        return ADD_DATA

    elif 'description' not in context.user_data:
        context.user_data['description'] = update.message.text
        await update.message.reply_text("Введите приметы :")
        return ADD_DATA

    elif 'features' not in context.user_data:
        context.user_data['features'] = update.message.text

        # Все данные собраны, отображаем для подтверждения
        nickname = context.user_data['nickname']
        location = context.user_data['location']
        breed = context.user_data['breed']
        color = context.user_data['color']
        description = context.user_data['description']
        features = context.user_data['features']

        await update.message.reply_text(
            f"Кличка: {nickname}\n"
            f"Место: {location}\n"
            f"Порода: {breed}\n"
            f"Окраска: {color}\n"
            f"Приметы: {features}\n"
            f"Описание: {description}\n"
            "Подтвердите объявление или нажмите Отмена для возврата.",
            reply_markup=ReplyKeyboardMarkup(
                [["Всё верно", "Отмена"]],
                one_time_keyboard=True,
                resize_keyboard=True
            )
        )
        return CONFIRMATION  # Переход к этапу подтверждения

    # Если что-то пошло не так
    await update.message.reply_text("Произошла ошибка. Пожалуйста, начните заново.")
    return await main_menu(update, context)

# Обработка подтверждения объявления
# Добавление записи о животном (потерянном или найденном)
async def handle_confirmation(update: Update, context: CallbackContext) -> int:
    choice = update.message.text
    if choice == "Отмена":
        await update.message.reply_text("Добавление отменено.")
        return await main_menu(update, context)

    if choice == "Всё верно":
        # Получаем данные
        photo_path = context.user_data['photo_path']
        nickname = context.user_data['nickname'] if 'nickname' in context.user_data else None
        location = context.user_data['location']
        breed = context.user_data['breed']
        color = context.user_data['color']
        features = context.user_data['features']
        description = context.user_data['description']
        status = "потеряна" if context.user_data.get('is_searching', False) else "найдена на улице"
        user_contact = update.message.chat.username

        conn = sqlite3.connect("animals.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO animals (photo_path, nickname, location, breed, color, features, description, status, user_contact) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (photo_path, nickname, location, breed, color, features, description, status, user_contact)
        )
        conn.commit()
        conn.close()

        await update.message.reply_text("Ваше объявление успешно добавлено!")
        return await main_menu(update, context)
    else:
        await update.message.reply_text("Неверный выбор, пожалуйста, выберите 'Всё верно' или 'Отмена'.")
        return CONFIRMATION

async def confirm_continue(update: Update, context: CallbackContext) -> int:
    """Подтверждает, продолжает ли пользователь поиск."""
    if update.message.text == "Да":
        context.user_data['current_ad_index'] = 0
        await show_ads(update, context)
    else:
        await update.message.reply_text("Поиск завершен.")
        return ConversationHandler.END


# Главная функция
def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            ADD_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, add_photo)],
            ADD_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_data)],
            CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation)],
            SHOW_ADS: [
                CallbackQueryHandler(like_ad, pattern="^like$"),
                CallbackQueryHandler(next_ad, pattern="^next_ad$"),
                CallbackQueryHandler(cancel, pattern="^cancel$")

            ],
            CONFIRM_CONTINUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_continue)],
        },
        fallbacks=[MessageHandler(filters.ALL, handle_unrelated_message)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
