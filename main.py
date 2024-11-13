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
from sentence_transformers import SentenceTransformer
import sqlite3
import numpy as np
from transformers import BertModel, BertTokenizer
from sklearn.metrics.pairwise import cosine_similarity
import torch

is_searching = None

# Инициализация модели и токенизатора
tokenizer = BertTokenizer.from_pretrained('bert-base-multilingual-cased')
model = BertModel.from_pretrained('bert-base-multilingual-cased')

TOKEN = "7704971887:AAGz0lHUYyv0BsLJdnV9sS50vCQgh2bM9G8"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

logger = logging.getLogger(__name__)

# Состояния для пользователей, которые ищут
MAIN_MENU, CHOOSE_ACTION, SEARCH_ADD_PHOTO, SEARCH_ADD_DATA, SEARCH_CONFIRMATION = range(5)

# Состояния для пользователей, которые хотят найти
FIND_SHOW_ADS, FIND_ADD_PHOTO, FIND_ADD_DATA, FIND_LIKE_AD, FIND_NEXT_AD, FIND_CONFIRM_CONTINUE, FIND_SHOW_AD_LIST = range(5, 12)

# Состояния для управления объявлениями
CHOOSE_ACTION_LIST, EDIT_ANNOUNCEMENT, DELETE_ANNOUNCEMENT = range(12, 15)

SELECT_AD_FOR_RECOMMENDATION = 16

async def start(update: Update, context: CallbackContext) -> int:
    logger.info("Вызвана команда start menu")

    # Обновляем список кнопок
    keyboard = [
        [KeyboardButton("Разместить объявление о потерянном животном")],
        [KeyboardButton("Просмотреть найденных животных")],
        [KeyboardButton("Разместить объявление о найденном животном")],
        [KeyboardButton("Посмотреть мои объявления"), KeyboardButton("Отмена")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    logger.info("Команда /start получена от %s", update.message.from_user.username)

    await update.message.reply_text("Добро пожаловать!", reply_markup=reply_markup)
    return MAIN_MENU


async def main_menu(update: Update, context: CallbackContext) -> int:
    logger.info("Вызвана команда main menu")

    context.user_data.clear()

    # Обновляем список кнопок
    keyboard = [
        [KeyboardButton("Разместить объявление о потерянном животном")],
        [KeyboardButton("Просмотреть найденных животных")],
        [KeyboardButton("Разместить объявление о найденном животном")],
        [KeyboardButton("Посмотреть мои объявления"), KeyboardButton("Отмена")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    # Проверяем, был ли вызов через callback_query (например, inline кнопка)
    if update.callback_query:
        await update.callback_query.answer()

        # Если есть текстовое сообщение в callback_query, редактируем его
        if update.callback_query.message and update.callback_query.message.text:
            await update.callback_query.message.edit_text("Выберите действие:", reply_markup=reply_markup)
        else:
            # Если текстовое сообщение отсутствует, отправляем новое сообщение
            logger.error("Сообщение не содержит текста, редактирование не выполнено.")
            await update.callback_query.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    else:
        # Если это обычное сообщение, просто отправляем ответ с кнопками
        await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)

    return CHOOSE_ACTION  # Переход в состояние выбора действия



# Обработка текстовых сообщений не по теме
async def handle_unrelated_message(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Извините, я не понимаю это сообщение. Пожалуйста, попробуйте выбрать действие '
                                    'из меню, нажать кнопку "Отмена" или отправьте команду /start для начала. '
                                    'Что-то из этого Вам точно поможет!')
# Убедитесь, что вы возвращаете правильные состояния, которые определены в ConversationHandler
async def choose_action(update: Update, context: CallbackContext) -> int:
    global is_searching

    user_choice = update.message.text.strip()
    logger.info("Выбор от %s: %s", update.message.from_user.username, user_choice)

    # Обработка отмены действия
    if user_choice == "Отмена":
        logger.info("Отмена действия от %s", update.message.from_user.username)
        await update.message.reply_text("Вы отменили текущую операцию.")
        return MAIN_MENU

    # Обработка выбора для размещения объявления о найденном животном
    elif user_choice == "Разместить объявление о найденном животном":
        is_searching = False
        await update.message.reply_text("Пожалуйста, заполните все данные для последующего успешного поиска.")
        await update.message.reply_text('Отправьте фото или нажмите "Отмена" для возврата.')
        return SEARCH_ADD_PHOTO

    # Обработка выбора для размещения объявления о потерянном животном
    elif user_choice == "Разместить объявление о потерянном животном":
        is_searching = True
        await update.message.reply_text("Пожалуйста, заполните все данные для последующего успешного поиска.")
        await update.message.reply_text('Отправьте фото или нажмите "Отмена" для возврата.')
        return FIND_ADD_PHOTO

    # Просмотр найденных животных
    elif user_choice == "Просмотреть найденных животных":
        logger.info("Выбор просмотреть найденных животных от %s: %s", update.message.from_user.username, user_choice)
        await show_my_announcements(update, context)
        return MAIN_MENU

    # Просмотр моих объявлений
    elif user_choice == "Посмотреть мои объявления":
        await show_my_announcements(update, context)
        return MAIN_MENU

    # Обработка выбора числа (номер объявления)
    try:
        user_choice_num = int(user_choice)  # Преобразуем в число
        logger.info("Получен выбор номера объявления: %d", user_choice_num)

        # Тут будет логика для обработки выбора номера объявления
        # Например, если это номер объявления, запуск подбора рекомендаций
        await handle_selected_ad(update, context, user_choice_num)
        return MAIN_MENU  # Возвращаем в основное меню после обработки выбора

    except ValueError:
        # Если введено не число, выводим предупреждение
        logger.warning("Неизвестный выбор@@@: %s", user_choice)
        await update.message.reply_text("Пожалуйста, введите корректный номер объявления.")
        return MAIN_MENU  # Возвращаем в основное меню


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
        await update.message.reply_text("Нет объявлений.")
        return ConversationHandler.END

    context.user_data['ads'] = ads
    context.user_data['current_ad_index'] = 0

    # Отображаем первое объявление
    await display_current_ad(update, context)
    return FIND_SHOW_ADS

def get_bert_embedding(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    outputs = model(**inputs)
    return outputs.last_hidden_state.mean(dim=1)


async def recommend_ads(update: Update, user_text, context):
    # Получение вектора запроса
    user_vector = get_bert_embedding(user_text)

    # Получение породы искомого животного из user_data
    search_breed = context.user_data.get('search_breed', None)

    # Получение всех объявлений из БД
    conn = sqlite3.connect("animals.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, photo_path, nickname, location, breed, color, features, description, user_contact FROM animals")
    ads = cursor.fetchall()
    conn.close()

    # Инициализация списков для объявлений с той же породой и для остальных
    breed_priority_ads = []
    other_ads = []

    # Расчет косинусного сходства для каждого объявления
    for ad in ads:
        ad_text = (
            f"Кличка: {ad[2]}\nМесто: {ad[3]}\nПорода: {ad[4]}\nОкраска: {ad[5]}\nПриметы: {ad[6]}\nОписание: {ad[7]}"
        )
        ad_vector = get_bert_embedding(ad_text)
        similarity = cosine_similarity(user_vector.detach().numpy(), ad_vector.detach().numpy())[0][0]

        # Если порода совпадает с искомой, добавляем в список с приоритетом
        if ad[4] == search_breed:
            breed_priority_ads.append((similarity, ad))
        else:
            other_ads.append((similarity, ad))

    # Сортировка по убыванию сходства
    sorted_breed_priority_ads = sorted(breed_priority_ads, key=lambda x: x[0], reverse=True)
    sorted_other_ads = sorted(other_ads, key=lambda x: x[0], reverse=True)

    # Объединение приоритетных объявлений и остальных
    sorted_ads = [ad for _, ad in sorted_breed_priority_ads] + [ad for _, ad in sorted_other_ads]

    # Сохранение в context.user_data для отображения
    context.user_data['ads'] = sorted_ads

    # Отображение текущего объявления
    await display_current_ad(update, context)


import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)


async def display_current_ad(update: Update, context: CallbackContext):
    # Определяем пользователя на основе типа обновления (сообщение или callback-запрос)
    user = (update.message.from_user.username if update.message
            else update.callback_query.from_user.username if update.callback_query
    else None)

    if not user:
        logger.error("Не удалось получить информацию о пользователе.")
        return

    # Логируем переход пользователя к следующему объявлению
    logger.info(f"Пользователь {user} переходит к следующему объявлению")

    # Получаем список объявлений из контекста и текущий индекс
    ads = context.user_data.get('ads', [])
    index = context.user_data.get('current_ad_index', 0)

    # Проверка пустоты списка объявлений
    if not ads:
        message = "Объявлений нет."
        if update.message:
            await update.message.reply_text(message)
        else:
            await update.callback_query.message.reply_text(message)
        logger.info(f"Список объявлений пуст для пользователя {user}")
        return

    # Проверяем и корректируем индекс для цикличного просмотра объявлений
    if index >= len(ads):
        index = 0
        context.user_data['current_ad_index'] = index  # Сброс индекса

    # Получаем текущее объявление
    ad = ads[index]
    ad_text = (
        f"Кличка: {ad[2]}\n"
        f"Место: {ad[3]}\n"
        f"Порода: {ad[4]}\n"
        f"Окраска: {ad[5]}\n"
        f"Приметы: {ad[6]}\n"
        f"Описание: {ad[7]}"
    )

    # Логирование проверки порядка пород в объявлениях
    logger.info(f"Отфильтрованные объявления для {user}: {[ad[4] for ad in ads]}")

    # Кнопки для взаимодействия
    buttons = [
        [InlineKeyboardButton("Лайк", callback_data="like")],
        [InlineKeyboardButton("Следующее объявление", callback_data="next_ad")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Проверка наличия фото в объявлении
    if ad[1]:
        # Логируем отправку фото
        logger.info(f"Отправка фото объявления с ID {ad[0]} для пользователя {user}. Текущий индекс: {index}")
        if update.message:
            await update.message.reply_photo(photo=open(ad[1], 'rb'), caption=ad_text, reply_markup=reply_markup)
        else:
            await update.callback_query.message.reply_photo(photo=open(ad[1], 'rb'), caption=ad_text,
                                                            reply_markup=reply_markup)
    else:
        # Логируем отправку текста
        logger.info(f"Отправка текста объявления с ID {ad[0]} для пользователя {user}. Текущий индекс: {index}")
        if update.message:
            await update.message.reply_text(ad_text, reply_markup=reply_markup)
        else:
            await update.callback_query.message.reply_text(ad_text, reply_markup=reply_markup)

    # Завершаем callback-запрос для Telegram
    if update.callback_query:
        await update.callback_query.answer()

    # Обновляем индекс для следующего объявления
    context.user_data['current_ad_index'] = index + 1


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
        [InlineKeyboardButton("Нет, завершить", callback_data="stop_search")]
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
    if query.message.text:
        # Редактируем текст сообщения
        await query.edit_message_text(
            f"Контактный юзернейм автора объявления: @{added_by_username}\n"
            "Хотите продолжить поиск?",
            reply_markup=reply_markup
        )
    elif query.message.caption:
        # Редактируем подпись сообщения с фото
        await query.edit_message_caption(
            caption=f"Контактный юзернейм автора объявления: @{added_by_username}\n"
                    "Хотите продолжить поиск?",
            reply_markup=reply_markup
        )
    else:
        logger.error("Невозможно редактировать сообщение, так как в нем нет ни текста, ни подписи.")
        await query.answer("Ошибка: нет текста для редактирования.", show_alert=True)

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
            await recommend_ads(update, context)  # Функция отображения объявления
        else:
            await update.message.reply_text("Больше нет доступных объявлений.")
            return ConversationHandler.END

    elif user_response == "Нет":
        # Отображаем главное меню
        if update.message:
            await update.message.reply_text("Возвращаемся в главное меню.")
            return await main_menu(update, context)  # Возвращаемся к главному меню
        elif update.callback_query:
            await update.callback_query.answer()  # отвечаем на callback_query
            await update.callback_query.message.edit_text("Возвращаемся в главное меню.")
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
        await recommend_ads(update, context)
        return FIND_CONFIRM_CONTINUE
    else:
        await query.answer("Нет больше объявлений для отображения.")
        return ConversationHandler.END


# Функция для обработки нажатия кнопки "Нет"
async def stop_search(update: Update, context: CallbackContext) -> int:
    logger.info("Пользователь завершил поиск")

    query = update.callback_query or update.message
    # Отправляем главное меню или сообщение о завершении
    if query.message.text:
        await query.edit_message_text("Возвращаемся в главное меню.")
    else:
        # Если текста нет, выполняем другое действие или просто игнорируем
        logging.info("Сообщение не содержит текста, редактирование не выполнено.")

    # Отправляем сообщение с кнопками главного меню
    return await main_menu(update, context)


async def next_ad(update: Update, context: CallbackContext) -> int:
    logger.info("next_ad вызван")

    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Ошибка при ответе на callback: {e}")

    # Инициализируем 'current_ad_index', если его нет
    if 'current_ad_index' not in context.user_data:
        context.user_data['current_ad_index'] = 0  # Устанавливаем начальное значение

    # Увеличиваем индекс для перехода к следующему объявлению
    context.user_data['current_ad_index'] += 1
    index = context.user_data['current_ad_index']
    ads = context.user_data.get('ads', [])

    # Проверка: достигли ли конца списка объявлений
    if index >= len(ads):
        try:
            # Проверка на текст в последнем сообщении
            if query.message.text:
                await query.edit_message_text("Объявления закончились.")
            else:
                await query.message.reply_text("Объявления закончились.")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения о завершении объявлений: {e}")
        return ConversationHandler.END

    # Логируем информацию о переходе к следующему объявлению
    user = update.callback_query.from_user if update.callback_query else update.message.from_user
    logger.info("Пользователь %s перешел к следующему объявлению с ID %d", user.username, ads[index][0])

    # Переход к следующему объявлению с использованием функции `display_current_ad`
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

    if update.message.text == "Отмена":
        context.user_data.clear()
        await update.message.reply_text("Добавление отменено.")
        await main_menu(update, context)
        return MAIN_MENU

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
        await main_menu(update, context)
        return MAIN_MENU

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
        await update.message.reply_text("Введите описание кошки/собаки, места где Вы её видели последний раз:")
        return SEARCH_ADD_DATA

    elif 'description' not in context.user_data:
        context.user_data['description'] = update.message.text
        await update.message.reply_text("Введите приметы:")
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

    global is_searching
    choice = update.message.text
    if choice == "Отмена":
        await update.message.reply_text("Добавление отменено.")
        return MAIN_MENU

    if choice == "Всё верно":
        # Получаем данные
        photo_path = context.user_data.get('photo_path')
        nickname = context.user_data.get('nickname')
        location = context.user_data.get('location')
        breed = context.user_data.get('breed')
        color = context.user_data.get('color')
        features = context.user_data.get('features')
        description = context.user_data.get('description')

        # Проверяем значение is_searching
        status = "ищут" if is_searching is True else "найдена на улице"
        logger.info("Статус перед записью в БД: %s", status)  # Проверка перед записью

        user_contact = update.message.chat.username

        # Сохраняем данные в БД
        conn = sqlite3.connect("animals.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO animals (photo_path, nickname, location, breed, color, features, description, status, user_contact) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (photo_path, nickname, location, breed, color, features, description, status, user_contact)
        )
        conn.commit()
        conn.close()

        # Очистите статус и все данные, чтобы избежать повторного добавления
        context.user_data.clear()

        await update.message.reply_text("Ваше объявление успешно добавлено!")

        return await main_menu(update, context)
    else:
        await update.message.reply_text("Неверный выбор, пожалуйста, выберите 'Всё верно' или 'Отмена'.")
        return SEARCH_CONFIRMATION

# Данные объявлений
user_announcements = {}


"""
async def show_my_announcements(update: Update, context: CallbackContext) -> int:
    logger.info("Начинаем показывать объявления пользователя.")

    user = update.message.from_user  # Используем update.message для обычных кнопок
    user_id = user.username

    # Получаем объявления пользователя из базы данных
    conn = sqlite3.connect("animals.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nickname, location, breed, color, description FROM animals WHERE user_contact = ?",
        (user_id,)
    )
    announcements = cursor.fetchall()
    conn.close()

    if not announcements:
        await update.message.reply_text("У вас нет размещенных объявлений.")
        return CHOOSE_ACTION_LIST

    # Формируем текст с объявлениями
    text = "Ваши объявления:\n"
    for i, announcement in enumerate(announcements, 1):
        text += f"{i}. {announcement[1]} - {announcement[2]} - {announcement[3]} - {announcement[4]}\n"

    context.user_data['user_announcements'] = announcements
    await update.message.reply_text(text)

    keyboard = [
        [KeyboardButton("Редактировать")],
        [KeyboardButton("Удалить"), KeyboardButton("Отмена")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)
    logger.info("Отправлено сообщение с объявлениями и кнопками.")
    return CHOOSE_ACTION_LIST
"""

# Показать объявления пользователя
async def show_my_announcements(update: Update, context: CallbackContext) -> int:
    logger.info("Начинаем показывать объявления пользователя.")
    user = update.message.from_user
    user_id = user.username

    # Получаем объявления пользователя с отметкой "ищут" из базы данных
    conn = sqlite3.connect("animals.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, nickname, location, breed, color, description FROM animals WHERE user_contact = ? AND status = 'ищут'",
        (user_id,)
    )
    announcements = cursor.fetchall()
    conn.close()

    if not announcements:
        await update.message.reply_text("У вас нет активных объявлений, отмеченных как 'ищут'.")
        return CHOOSE_ACTION_LIST

    # Формируем текст для отображения объявлений с номерами
    text = "Ваши объявления (ищут):\n"
    for i, announcement in enumerate(announcements, 1):
        text += f"{i}. {announcement[1]} - {announcement[2]} - {announcement[3]} - {announcement[4]}\n"

    context.user_data['user_announcements'] = announcements
    await update.message.reply_text(text)
    await update.message.reply_text("Введите номер объявления, для которого хотите получить рекомендации:")

    return SELECT_AD_FOR_RECOMMENDATION  # Переход к следующему шагу
# Обработать выбор объявления для поиска рекомендаций
async def handle_selected_ad(update: Update, context: CallbackContext, user_choice_num) -> int:
    announcements = context.user_data.get('user_announcements', [])

    # Проверка, что номер объявления в пределах доступных
    if user_choice_num < 1 or user_choice_num > len(announcements):
        await update.message.reply_text("Неверный номер объявления. Попробуйте еще раз.")
        return SELECT_AD_FOR_RECOMMENDATION  # Возвращаем к выбору объявления

    # Преобразуем номер в индекс (минус 1, так как индексация в списках начинается с 0)
    selected_ad = announcements[user_choice_num - 1]

    # Формируем текст объявления
    ad_text = (
        f"Кличка: {selected_ad[1]}\n"
        f"Место: {selected_ad[2]}\n"
        f"Порода: {selected_ad[3]}\n"
        f"Окраска: {selected_ad[4]}\n"
        f"Описание: {selected_ad[5]}\n"
    )

    logger.info(f"Запущен подбор рекомендаций на основе объявления ID {selected_ad[0]}")

    # Запускаем поиск рекомендаций по тексту объявления
    await recommend_ads(update, ad_text, context)

    return CHOOSE_ACTION_LIST  # Переход к отображению рекомендованных объявлений


"""

async def action(update: Update, context: CallbackContext):
    user_choice = update.message.text.strip()  # Удаление пробелов

    if user_choice == "Отмена":
        logger.info("Отмена действия от %s", update.message.from_user.username)
        await update.message.reply_text("Вы отменили текущую операцию.")
        return await main_menu(update, context)

    elif user_choice == "Редактировать":
        logger.info(f"Редактировать от {update.message.from_user.username}")
        await update.message.reply_text("Введите номер объявления, которое хотите отредактировать.")
        #return EDIT_ANNOUNCEMENT
        return await edit_announcement(update, context)

    elif user_choice == "Удалить":
        logger.info(f"Удалить от {update.message.from_user.username}")
        await update.message.reply_text("Введите номер объявления, которое хотите удалить.")
        return DELETE_ANNOUNCEMENT

    else:
        logger.warning(f"Неизвестный выбор: {user_choice}")
        return CHOOSE_ACTION_LIST

async def edit_announcement(update: Update, context: CallbackContext):
    logger.info("Пользователь вызвал edit_announcement")

    try:
        announcement_number = int(update.message.text)
        announcements = context.user_data.get('user_announcements', [])
        if 1 <= announcement_number <= len(announcements):
            context.user_data['announcement_number'] = announcement_number
            update.message.reply_text("Пожалуйста, введите новый текст объявления.")
            return EDIT_ANNOUNCEMENT
        else:
            update.message.reply_text("Номер объявления некорректен. Попробуйте снова.")
            return EDIT_ANNOUNCEMENT
    except ValueError:
        update.message.reply_text("Пожалуйста, введите корректный номер объявления.")
        return EDIT_ANNOUNCEMENT

async def update_announcement(update: Update, context: CallbackContext):
    logger.info("Пользователь начал обновление объявления")

    announcement_number = context.user_data.get('announcement_number')
    if announcement_number:
        new_text = update.message.text
        announcements = context.user_data.get('user_announcements', [])

        # Обновляем только текст объявления
        announcements[announcement_number - 1] = (new_text,)
        context.user_data['user_announcements'] = announcements

        user_id = update.message.from_user.id
        conn = sqlite3.connect("animals.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE animals SET description = ? WHERE id = ? AND user_contact = ?",
            (new_text, announcements[announcement_number - 1][0], user_id)
        )
        conn.commit()
        conn.close()

        update.message.reply_text("Ваше объявление успешно обновлено!")

        return await show_my_announcements(update, context)

    return ConversationHandler.END

async def delete_announcement(update: Update, context: CallbackContext):
    logger.info("Пользователь начал удаление объявления")

    try:
        announcement_number = int(update.message.text)
        announcements = context.user_data.get('user_announcements', [])
        if 1 <= announcement_number <= len(announcements):
            user_id = update.message.from_user.id
            announcement_id = announcements[announcement_number - 1][0]
            conn = sqlite3.connect("animals.db")
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM animals WHERE id = ? AND user_contact = ?",
                (announcement_id, user_id)
            )
            conn.commit()
            conn.close()

            del announcements[announcement_number - 1]
            context.user_data['user_announcements'] = announcements

            update.message.reply_text("Ваше объявление успешно удалено.")

            return await show_my_announcements(update, context)
        else:
            update.message.reply_text("Номер объявления некорректен. Попробуйте снова.")
            return DELETE_ANNOUNCEMENT
    except ValueError:
        update.message.reply_text("Пожалуйста, введите корректный номер объявления.")
        return DELETE_ANNOUNCEMENT

"""

def show_announcements(update: Update, context: CallbackContext):
    return show_my_announcements(update, context)

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
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            CHOOSE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_action)],
            SEARCH_ADD_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, add_photo)],
            FIND_ADD_PHOTO: [MessageHandler(filters.PHOTO | filters.TEXT, add_photo)],
            SEARCH_ADD_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_data)],
            FIND_LIKE_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_data)],
            SEARCH_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirmation)],

            #EDIT_ANNOUNCEMENT: [
            #    MessageHandler(filters.TEXT & ~filters.COMMAND, edit_announcement),
            #    MessageHandler(filters.TEXT & ~filters.COMMAND, update_announcement)
            #],
            #DELETE_ANNOUNCEMENT: [
            #    MessageHandler(filters.TEXT & ~filters.COMMAND, delete_announcement)
            #],
            #CHOOSE_ACTION_LIST: [
            #    CallbackQueryHandler(edit_announcement, pattern="^(edit)$"),
            #    CallbackQueryHandler(delete_announcement, pattern="^(delete)$"),
            #],
            CHOOSE_ACTION_LIST: [
                CommandHandler("show_my_announcements", show_my_announcements)
            ],
            SELECT_AD_FOR_RECOMMENDATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_selected_ad)
            ],
            FIND_SHOW_ADS: [
                CallbackQueryHandler(like_ad, pattern="^like$"),
                CallbackQueryHandler(next_ad, pattern="^next_ad$"),
            ],
            FIND_CONFIRM_CONTINUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_continue)],
        },
        #fallbacks=[CommandHandler('start', main_menu)],
        fallbacks=[MessageHandler(filters.ALL, handle_unrelated_message)],
    )

    # Регистрация обработчиков
    application.add_handler(CallbackQueryHandler(like_ad, pattern="^like$"))
    application.add_handler(CallbackQueryHandler(next_ad, pattern="^next_ad$"))
    application.add_handler(CallbackQueryHandler(stop_search, pattern="^stop_search$"))

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unrelated_message))

    # Запуск бота
    application.run_polling()


if __name__ == '__main__':
    main()
