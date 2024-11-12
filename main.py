import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
import sqlite3
import os
from PIL import Image
import torch
from torchvision import models, transforms
from torchvision.models import ResNet50_Weights
from telegram import ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
import sqlite3
from telegram.ext import CallbackQueryHandler

TOKEN = "7704971887:AAGz0lHUYyv0BsLJdnV9sS50vCQgh2bM9G8"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)


# Состояния для пользователей, которые ищут
SEARCH_CHOOSE_ACTION, SEARCH_ADD_PHOTO, SEARCH_ADD_DATA, SEARCH_CONFIRMATION = range(4)

# Состояния для пользователей, которые хотят найти
FIND_SHOW_ADS, FIND_LIKE_AD, FIND_NEXT_AD, FIND_CONFIRM_CONTINUE, FIND_SHOW_AD_LIST = range(4, 9)

# Инициализация модели и устройства
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = models.resnet50(weights=ResNet50_Weights.IMAGENET1K_V1).to(device)
model.eval()

async def start(update: Update, context: CallbackContext) -> int:
    logger.info("Команда /start получена от %s", update.message.from_user.username)
    await update.message.reply_text("Добро пожаловать!")
    return await main_menu(update, context)

async def main_menu(update: Update, context: CallbackContext) -> int:
    logger.info("Отображение главного меню для %s", update.message.from_user.username)
    keyboard = [
        [KeyboardButton("Я хочу найти"), KeyboardButton("Я хочу помочь найти")],
        [KeyboardButton("Отмена")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    return SEARCH_CHOOSE_ACTION


# Обработка текстовых сообщений не по теме
async def handle_unrelated_message(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Извините, я не понимаю это сообщение. Пожалуйста, попробуйте выбрать действие из меню, нажать кнопку 'Отмена' или отправьте команду /start для начала. Что-то из этого Вам точно поможет!")


async def choose_action(update: Update, context: CallbackContext) -> int:
    user_choice = update.message.text
    logger.info("Выбор от %s: %s",  update.message.from_user.username, user_choice)

    if user_choice == "Отмена":
        logger.info("Отмена действия от %s", update.message.from_user.username)
        await update.message.reply_text("Вы отменили текущую операцию.")
        return await main_menu(update, context)
    elif user_choice == "Я хочу помочь найти":
        logger.info('%s нажал "Я хочу помочь найти"', update.message.from_user.username)
        context.user_data['is_searching'] = True
        await update.message.reply_text("Пожалуйста, заполните все данные для последующего успешного "
                                        "поиска хозяина потерянного животного, либо поставьте прочерк.")
        await update.message.reply_text('Отправьте фото, или нажмите "Отмена" для возврата.')
        return SEARCH_ADD_PHOTO
    elif user_choice == "Я хочу найти":
        logger.info("Переход к отображению объявлений для %s", update.message.from_user.username)
        await show_ads(update, context)
        return ConversationHandler.END
    else:
        logger.warning("Неизвестный выбор: %s", user_choice)
        return await main_menu(update, context)


# Обработка текстовых сообщений не по теме
async def handle_unrelated_message(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Извините, я не понимаю это сообщение. Пожалуйста, попробуйте выбрать действие из меню, нажать кнопку 'Отмена' или отправьте команду /start для начала. Что-то из этого Вам точно поможет!")


async def show_ads(update: Update, context: CallbackContext) -> int:
    # Извлечение данных из базы
    conn = sqlite3.connect("animals.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, photo_path, nickname, location, breed, color, features, description, user_contact FROM animals WHERE status = ?",
        ("найдена на улице",)
    )
    ads = cursor.fetchall()
    conn.close()

    if not ads:
        await update.message.reply_text("Пока нет объявлений.")
        return ConversationHandler.END

    context.user_data['ads'] = ads
    context.user_data['current_ad_index'] = 0

    # Отображаем первое объявление
    await display_current_ad(update, context)
    return FIND_SHOW_ADS


async def display_current_ad(update: Update, context: CallbackContext):
    # Проверяем, откуда пришло обновление (сообщение или callback)
    if update.message:
        user = update.message.from_user.username  # Это для обычного сообщения
    elif update.callback_query:
        user = update.callback_query.from_user.username  # Это для callback-запроса
    else:
        logger.error("Не удалось получить информацию о пользователе, так как нет ни message, ни callback_query.")
        return

    # Логирование информации о пользователе
    logger.info(f"Пользователь {user} переходит к следующему объявлению")

    # Обрабатываем следующее объявление
    ads = context.user_data.get('ads', [])
    index = context.user_data.get('current_ad_index', 0)

    if not ads:
        await update.message.reply_text(
            "Объявлений нет.") if update.message else await update.callback_query.message.reply_text("Объявлений нет.")
        logger.info("Список объявлений пуст для пользователя %s", user)
        return

    if index >= len(ads):
        context.user_data['current_ad_index'] = 0
        index = 0

    ad = ads[index]
    ad_text = (
        f"Кличка: {ad[2]}\n"
        f"Место: {ad[3]}\n"
        f"Порода: {ad[4]}\n"
        f"Окраска: {ad[5]}\n"
        f"Приметы: {ad[6]}\n"
        f"Описание: {ad[7]}\n"
    )

    buttons = [
        [InlineKeyboardButton("Лайк", callback_data="like")],
        [InlineKeyboardButton("Следующее объявление", callback_data="next_ad")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    if ad[1]:
        # Логируем отправку фото объявления
        logger.info(
            "Отправка фото объявления с ID %d для пользователя %s. Текущий индекс объявления: %d",
            ad[0], user, index
        )
        if update.message:
            await update.message.reply_photo(photo=open(ad[1], 'rb'), caption=ad_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.reply_photo(photo=open(ad[1], 'rb'), caption=ad_text,
                                                            reply_markup=reply_markup)
    else:
        # Логируем отправку текста объявления без фото
        logger.info(
            "Отправка текста объявления с ID %d для пользователя %s. Текущий индекс объявления: %d",
            ad[0], user, index
        )
        if update.message:
            await update.message.reply_text(ad_text, reply_markup=reply_markup)
        elif update.callback_query:
            await update.callback_query.message.reply_text(ad_text, reply_markup=reply_markup)


# Измененная версия для like_ad с ReplyKeyboardMarkup

async def like_ad(update: Update, context: CallbackContext) -> int:
    logger.info("like_ad вызван")

    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Ошибка при ответе на callback: {e}")

    ads = context.user_data.get('ads', [])
    index = context.user_data.get('current_ad_index', 0)

    if index >= len(ads):
        await query.edit_message_text("Нет доступных объявлений.")
        return ConversationHandler.END

    ad = ads[index]
    added_by_username = ad[8]

    # Получаем данные пользователя из callback_query
    if update.callback_query:
        user = update.callback_query.from_user  # Используем from_user из callback_query
        logger.info("Пользователь %s нажал 'Лайк' на объявление с ID %d", user.username, ad[0])
    else:
        logger.warning("Не удалось получить информацию о пользователе, так как update.callback_query отсутствует.")

    # Изменяем кнопки
    buttons = [
        [InlineKeyboardButton("Да, продолжить", callback_data="next_ad")],
        [InlineKeyboardButton("Нет, завершить", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Если текстовое сообщение
    if query.message.text:
        # Редактируем текст сообщения
        await query.edit_message_text(
            f"Контактный юзернейм автора объявления: @{added_by_username}\n"
            "Хотите продолжить поиск?",
            reply_markup=reply_markup
        )
    # Если сообщение с изображением
    elif query.message.caption:
        # Редактируем подпись сообщения с фото
        await query.edit_message_caption(
            caption=f"Контактный юзернейм автора объявления: @{added_by_username}\n"
                    "Хотите продолжить поиск?",
            reply_markup=reply_markup
        )
    else:
        logger.error("Невозможно редактировать сообщение, так как в нем нет ни текста, ни подписи.")

    return FIND_CONFIRM_CONTINUE


async def confirm_continue(update: Update, context: CallbackContext) -> int:
    # Получаем ответ пользователя: если сообщение, то из message.text, если callback - то из callback.data
    user_response = update.message.text if update.message else update.callback_query.data

    # Обрабатываем ответ
    if user_response == "Да":
        # Переход к следующему объявлению
        ads = context.user_data.get('ads', [])
        index = context.user_data.get('current_ad_index', 0)

        if index + 1 < len(ads):
            context.user_data['current_ad_index'] = index + 1
            await display_current_ad(update, context)  # Функция отображения объявления
        else:
            await update.message.reply_text("Больше нет доступных объявлений.")
            return ConversationHandler.END

    elif user_response == "Нет":
        # Отображаем главное меню
        await update.message.reply_text("Главное меню. Пожалуйста, выберите одну из опций.")
        return await main_menu(update, context)  # Возвращаемся к главному меню

    return ConversationHandler.END

# Функция для обработки нажатия кнопки "Да"
async def continue_search(update: Update, context: CallbackContext) -> int:
    logger.info("Пользователь хочет продолжить поиск")

    query = update.callback_query or update.message
    ads = context.user_data.get('ads', [])
    index = context.user_data.get('current_ad_index', 0)

    if index + 1 < len(ads):
        context.user_data['current_ad_index'] = index + 1
        # Отправляем следующее объявление
        await display_current_ad(update, context)
        return FIND_CONFIRM_CONTINUE
    else:
        await query.answer("Нет больше объявлений для отображения.")
        return ConversationHandler.END


# Функция для обработки нажатия кнопки "Нет"
async def stop_search(update: Update, context: CallbackContext) -> int:
    logger.info("Пользователь завершил поиск")

    query = update.callback_query or update.message
    # Отправляем главное меню или сообщение о завершении
    await query.answer("Возвращаемся в главное меню.")
    await query.edit_message_text("Возвращаемся в главное меню.")
    # Здесь можно отправить сообщение с кнопками главного меню

    return await main_menu(update, context)


async def next_ad(update: Update, context: CallbackContext) -> int:
    logger.info("next_ad вызван")

    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Ошибка при ответе на callback: {e}")

    context.user_data['current_ad_index'] += 1
    index = context.user_data['current_ad_index']
    ads = context.user_data.get('ads', [])

    if index >= len(ads):
        await query.edit_message_text("Объявления закончились.")
        return ConversationHandler.END

    # Логируем информацию о переходе к следующему объявлению
    user = update.callback_query.from_user if update.callback_query else update.message.from_user
    logger.info("Пользователь %s перешел к следующему объявлению с ID %d", user.username, ads[index][0])

    await display_current_ad(update, context)
    return FIND_SHOW_ADS


async def confirm_continue(update: Update, context: CallbackContext) -> int:
    if update.message.text == "Да":
        context.user_data['current_ad_index'] = 0
        await show_ads(update, context)
    else:
        await update.message.reply_text("Поиск завершен.")
        return ConversationHandler.END


# Обработка добавления фото
async def add_photo(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()  # Очистка данных для новой анкеты
    entry_points = [CommandHandler("start", start)]

    if update.message.text == "Отмена":
        await update.message.reply_text("Добавление отменено.")
        return await main_menu(update, context)

    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправьте фото, или нажмите Отмена для возврата.")
        return SEARCH_ADD_PHOTO

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    photo_path = os.path.join("photos", f"{photo.file_id}.jpg")
    await photo_file.download_to_drive(photo_path)
    context.user_data['photo_path'] = photo_path

    await update.message.reply_text("Введите кличку кошки/собаки, если знаете:")
    return SEARCH_ADD_DATA


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
        return SEARCH_ADD_DATA

    elif 'location' not in context.user_data:
        context.user_data['location'] = update.message.text
        await update.message.reply_text("Введите породу кошки/собаки:")
        return SEARCH_ADD_DATA

    elif 'breed' not in context.user_data:
        context.user_data['breed'] = update.message.text
        await update.message.reply_text("Введите окраску:")
        return SEARCH_ADD_DATA

    elif 'color' not in context.user_data:
        context.user_data['color'] = update.message.text
        await update.message.reply_text("Введите описание кошки/собаки, места где Вы её видели:")
        return SEARCH_ADD_DATA

    elif 'description' not in context.user_data:
        context.user_data['description'] = update.message.text
        await update.message.reply_text("Введите приметы :")
        return SEARCH_ADD_DATA

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
        return SEARCH_CONFIRMATION  # Переход к этапу подтверждения

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
        return SEARCH_CONFIRMATION



# Основная функция
def main() -> None:
    application = ApplicationBuilder().token(TOKEN).build()

    # Подключение к базе данных
    conn = sqlite3.connect("animals.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS animals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_path TEXT NOT NULL,
            nickname TEXT,
            location TEXT NOT NULL,
            breed TEXT NOT NULL,
            color TEXT NOT NULL,
            features TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            user_contact TEXT NOT NULL
        );
    ''')
    conn.commit()
    conn.close()

    # Обработчики состояний
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SEARCH_CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            SEARCH_ADD_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, add_photo)],
            SEARCH_ADD_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_data)],
            SEARCH_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation)],
            FIND_SHOW_ADS: [
                CallbackQueryHandler(like_ad, pattern="^like$"),
                CallbackQueryHandler(next_ad, pattern="^next_ad$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$")
            ],
            FIND_CONFIRM_CONTINUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_continue)],
        },
        fallbacks=[MessageHandler(filters.ALL, handle_unrelated_message)],
    )

    # Регистрация обработчиков
    application.add_handler(CallbackQueryHandler(like_ad, pattern="^like$"))
    application.add_handler(CallbackQueryHandler(next_ad, pattern="^next_ad$"))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unrelated_message))

    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()
