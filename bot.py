import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")
SHOP_NAME = os.getenv("SHOP_NAME", "BLACK PREMIUM")
DB_PATH = os.getenv("DB_PATH", "shop.db")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Copy .env.example to .env and add your BotFather token.")

logging.basicConfig(level=logging.INFO)
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, price REAL NOT NULL,
            description TEXT DEFAULT '', photo TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER, product_id INTEGER, qty INTEGER DEFAULT 1,
            PRIMARY KEY(user_id, product_id)
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, username TEXT DEFAULT '',
            customer_name TEXT NOT NULL, contact TEXT NOT NULL,
            items TEXT NOT NULL, total REAL NOT NULL,
            status TEXT DEFAULT 'Новый', created_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, lang TEXT DEFAULT 'ru'
        )""")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_lang(user_id: int) -> str:
    with db() as con:
        row = con.execute("SELECT lang FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            con.execute("INSERT OR IGNORE INTO users(user_id,lang) VALUES(?, 'ru')", (user_id,))
            return "ru"
        return row["lang"]


TEXT = {
    "ru": {
        "welcome": "Добро пожаловать в <b>{shop}</b>.\n\nПремиальный сервис заказа товаров — быстро, удобно и в одном месте.",
        "catalog": "🛍 Каталог", "cart": "🛒 Корзина", "orders": "📦 Мои заказы",
        "support": "💬 Поддержка", "language": "🌐 Язык",
        "empty": "Пока здесь пусто. Загляните в каталог.",
        "added": "Добавлено в корзину.", "checkout": "✅ Оформить заказ",
        "clear": "🗑 Очистить корзину", "back": "⬅️ Назад",
        "name": "Напишите ваше имя для заказа:",
        "contact": "Оставьте контакт для связи (например, @username или номер телефона):",
        "created": "Заказ <b>№{id}</b> создан!\nСумма: <b>{total:.2f} €</b>\nМы свяжемся с вами для подтверждения и оплаты.",
        "no_orders": "У вас пока нет заказов.",
        "support_text": "По вопросам заказа напишите в поддержку: {support}",
        "support_missing": "Поддержка пока не настроена. Попробуйте позже.",
        "admin_only": "Эта команда доступна только администратору.",
        "unknown": "Не понял команду. Используйте кнопки меню.",
        "cart_title": "🛒 <b>Ваша корзина</b>\n",
        "orders_title": "📦 <b>Ваши заказы</b>\n",
        "empty_catalog": "Каталог пока пуст. Администратор может добавить товары командой /addproduct.",
        "select_product": "Выберите товар:",
        "qty": "Количество: {qty}",
        "deleted": "Корзина очищена.",
        "admin_help": "<b>Админ-команды</b>\n/addproduct Название|Цена|Описание|Фото_URL(необязательно)\n/products — список товаров\n/delproduct ID — удалить товар\n/orders — последние заказы\n/paid ID — отметить заказ оплаченным\n\nУкажите ADMIN_IDS в .env.",
        "product_added": "Товар добавлен с ID {id}.",
        "product_deleted": "Товар {id} удалён/скрыт.",
        "order_status": "Статус заказа обновлён.",
        "no_products": "Товаров пока нет.",
        "cancel": "Отменено."
    },
    "en": {
        "welcome": "Welcome to <b>{shop}</b>.\n\nA premium ordering experience — simple, fast and all in one place.",
        "catalog": "🛍 Catalog", "cart": "🛒 Cart", "orders": "📦 My orders",
        "support": "💬 Support", "language": "🌐 Language",
        "empty": "Nothing here yet. Visit the catalog.",
        "added": "Added to cart.", "checkout": "✅ Checkout",
        "clear": "🗑 Clear cart", "back": "⬅️ Back",
        "name": "Enter your name for the order:",
        "contact": "Enter a contact (for example, @username or phone number):",
        "created": "Order <b>#{id}</b> created!\nTotal: <b>{total:.2f} €</b>\nWe will contact you to confirm the order and payment.",
        "no_orders": "You have no orders yet.",
        "support_text": "For order support, contact: {support}",
        "support_missing": "Support is not configured yet. Please try later.",
        "admin_only": "This command is for administrators only.",
        "unknown": "I didn't understand. Please use the menu buttons.",
        "cart_title": "🛒 <b>Your cart</b>\n",
        "orders_title": "📦 <b>Your orders</b>\n",
        "empty_catalog": "The catalog is empty. Admin can add products using /addproduct.",
        "select_product": "Choose a product:",
        "qty": "Quantity: {qty}",
        "deleted": "Cart cleared.",
        "admin_help": "<b>Admin commands</b>\n/addproduct Title|Price|Description|Photo_URL(optional)\n/products — list products\n/delproduct ID — hide product\n/orders — latest orders\n/paid ID — mark order paid\nSet ADMIN_IDS in .env.",
        "product_added": "Product added with ID {id}.",
        "product_deleted": "Product {id} deleted/hidden.",
        "order_status": "Order status updated.",
        "no_products": "No products yet.",
        "cancel": "Cancelled."
    }
}


def t(user_id, key, **kwargs):
    lang = get_lang(user_id)
    return TEXT[lang][key].format(**kwargs)


def main_menu(uid):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(uid, "catalog")), KeyboardButton(text=t(uid, "cart"))],
            [KeyboardButton(text=t(uid, "orders")), KeyboardButton(text=t(uid, "support"))],
            [KeyboardButton(text=t(uid, "language"))]
        ],
        resize_keyboard=True
    )


def product_keyboard(product_id, uid):
    b = InlineKeyboardBuilder()
    b.button(text="➕ Добавить" if get_lang(uid) == "ru" else "➕ Add", callback_data=f"add:{product_id}")
    b.adjust(1)
    return b.as_markup()


def cart_keyboard(uid):
    b = InlineKeyboardBuilder()
    with db() as con:
        rows = con.execute("SELECT product_id, qty FROM cart WHERE user_id=?", (uid,)).fetchall()
    for row in rows:
        b.button(text=f"➖ {row['product_id']}", callback_data=f"remove:{row['product_id']}")
    if rows:
        b.button(text=t(uid, "checkout"), callback_data="checkout")
        b.button(text=t(uid, "clear"), callback_data="clearcart")
    b.button(text=t(uid, "back"), callback_data="home")
    b.adjust(2, 1, 1)
    return b.as_markup()


class Checkout(StatesGroup):
    name = State()
    contact = State()


@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    with db() as con:
        con.execute("INSERT OR IGNORE INTO users(user_id,lang) VALUES(?, 'ru')", (uid,))
    await message.answer(t(uid, "welcome", shop=SHOP_NAME), reply_markup=main_menu(uid))


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t(message.from_user.id, "cancel"), reply_markup=main_menu(message.from_user.id))


@dp.message(Command("admin"))
async def admin(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(t(message.from_user.id, "admin_only"))
    await message.answer(TEXT[get_lang(message.from_user.id)]["admin_help"])


@dp.message(Command("addproduct"))
async def add_product(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(t(message.from_user.id, "admin_only"))
    raw = message.text.partition(" ")[2]
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        return await message.answer("Формат: /addproduct Название|Цена|Описание|Фото_URL(необязательно)")
    try:
        title, price, description = parts[:3]
        photo = parts[3] if len(parts) > 3 else ""
        price_value = float(price.replace(",", "."))
        if price_value < 0:
            raise ValueError()
    except ValueError:
        return await message.answer("Проверь цену. Пример: /addproduct Футболка|19.90|Чёрная футболка")
    with db() as con:
        cur = con.execute("INSERT INTO products(title,price,description,photo) VALUES(?,?,?,?)",
                          (title, price_value, description, photo))
        pid = cur.lastrowid
    await message.answer(t(message.from_user.id, "product_added", id=pid))


@dp.message(Command("products"))
async def list_products_admin(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(t(message.from_user.id, "admin_only"))
    with db() as con:
        rows = con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall()
    if not rows:
        return await message.answer(t(message.from_user.id, "no_products"))
    await message.answer("\n".join(f"#{r['id']} — {r['title']} — {r['price']:.2f} €" for r in rows))


@dp.message(Command("delproduct"))
async def delete_product(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(t(message.from_user.id, "admin_only"))
    try:
        pid = int(message.text.split(maxsplit=1)[1])
    except (IndexError, ValueError):
        return await message.answer("Использование: /delproduct ID")
    with db() as con:
        con.execute("UPDATE products SET active=0 WHERE id=?", (pid,))
    await message.answer(t(message.from_user.id, "product_deleted", id=pid))


@dp.message(Command("orders"))
async def orders_command(message: Message):
    if not is_admin(message.from_user.id):
        return await show_user_orders(message)
    with db() as con:
        rows = con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 15").fetchall()
    if not rows:
        return await message.answer("Заказов пока нет.")
    lines = []
    for r in rows:
        lines.append(f"#{r['id']} | {r['status']} | {r['total']:.2f} €\n{r['customer_name']} | {r['contact']}\n{r['items']}\n{r['created_at']}")
    await message.answer("\n\n".join(lines))


@dp.message(Command("paid"))
async def mark_paid(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer(t(message.from_user.id, "admin_only"))
    try:
        oid = int(message.text.split(maxsplit=1)[1])
    except (IndexError, ValueError):
        return await message.answer("Использование: /paid ID")
    with db() as con:
        con.execute("UPDATE orders SET status='Оплачен' WHERE id=?", (oid,))
        row = con.execute("SELECT user_id FROM orders WHERE id=?", (oid,)).fetchone()
    if row:
        try:
            await bot.send_message(row["user_id"], f"✅ Заказ №{oid} отмечен как оплаченный.")
        except Exception:
            pass
    await message.answer(t(message.from_user.id, "order_status"))


async def show_catalog(message_or_callback, uid):
    with db() as con:
        rows = con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall()
    if not rows:
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer(t(uid, "empty_catalog"))
        else:
            await message_or_callback.message.answer(t(uid, "empty_catalog"))
        return
    target = message_or_callback.answer if isinstance(message_or_callback, Message) else message_or_callback.message.answer
    for r in rows:
        caption = f"<b>{r['title']}</b>\n{r['description']}\n\n💶 <b>{r['price']:.2f} €</b>"
        kb = product_keyboard(r["id"], uid)
        try:
            if r["photo"]:
                await bot.send_photo(uid, r["photo"], caption=caption, reply_markup=kb)
            else:
                await bot.send_message(uid, caption, reply_markup=kb)
        except Exception:
            await bot.send_message(uid, caption, reply_markup=kb)


async def show_cart(target, uid):
    with db() as con:
        rows = con.execute("""SELECT p.id,p.title,p.price,c.qty FROM cart c
            JOIN products p ON p.id=c.product_id WHERE c.user_id=? AND p.active=1""", (uid,)).fetchall()
    if not rows:
        await target.answer(t(uid, "empty"), reply_markup=main_menu(uid))
        return
    total = sum(r["price"] * r["qty"] for r in rows)
    text = t(uid, "cart_title")
    for r in rows:
        text += f"\n• {r['title']} × {r['qty']} — {r['price']*r['qty']:.2f} €"
    text += f"\n\n<b>Итого: {total:.2f} €</b>"
    await target.answer(text, reply_markup=cart_keyboard(uid))


async def show_user_orders(message):
    uid = message.from_user.id
    with db() as con:
        rows = con.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,)).fetchall()
    if not rows:
        return await message.answer(t(uid, "no_orders"))
    lines = [f"№{r['id']} — {r['status']} — {r['total']:.2f} €\n{r['created_at']}" for r in rows]
    await message.answer(t(uid, "orders_title") + "\n\n".join(lines))


@dp.message()
async def menu_router(message: Message, state: FSMContext):
    uid = message.from_user.id
    current = await state.get_state()
    if current == Checkout.name.state:
        name = message.text.strip()
        if len(name) < 2:
            return await message.answer("Введите имя минимум из двух символов.")
        await state.update_data(customer_name=name)
        await state.set_state(Checkout.contact)
        return await message.answer(t(uid, "contact"))
    if current == Checkout.contact.state:
        contact = message.text.strip()
        data = await state.get_data()
        with db() as con:
            rows = con.execute("""SELECT p.title,p.price,c.qty FROM cart c
                JOIN products p ON p.id=c.product_id WHERE c.user_id=? AND p.active=1""", (uid,)).fetchall()
            if not rows:
                await state.clear()
                return await message.answer(t(uid, "empty"), reply_markup=main_menu(uid))
            total = sum(r["price"] * r["qty"] for r in rows)
            items = "; ".join(f"{r['title']} x{r['qty']}" for r in rows)
            cur = con.execute("""INSERT INTO orders(user_id,username,customer_name,contact,items,total,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (uid, message.from_user.username or "", data["customer_name"], contact,
                 items, total, datetime.now().strftime("%Y-%m-%d %H:%M")))
            oid = cur.lastrowid
            con.execute("DELETE FROM cart WHERE user_id=?", (uid,))
        await state.clear()
        await message.answer(t(uid, "created", id=oid, total=total), reply_markup=main_menu(uid))
        for aid in ADMIN_IDS:
            try:
                await bot.send_message(aid, f"🆕 <b>Новый заказ №{oid}</b>\nКлиент: {data['customer_name']}\nКонтакт: {contact}\nTelegram: @{message.from_user.username or 'нет'}\nТовары: {items}\nСумма: {total:.2f} €\nОтметить оплату: /paid {oid}")
            except Exception:
                logging.exception("Could not notify admin")
        return

    text = (message.text or "").strip()
    if text in (t(uid, "catalog"), "🛍 Каталог", "🛍 Catalog"):
        return await show_catalog(message, uid)
    if text in (t(uid, "cart"), "🛒 Корзина", "🛒 Cart"):
        return await show_cart(message, uid)
    if text in (t(uid, "orders"), "📦 Мои заказы", "📦 My orders"):
        return await show_user_orders(message)
    if text in (t(uid, "support"), "💬 Поддержка", "💬 Support"):
        if SUPPORT_USERNAME:
            return await message.answer(t(uid, "support_text", support=f"@{SUPPORT_USERNAME}"))
        return await message.answer(t(uid, "support_missing"))
    if text in (t(uid, "language"), "🌐 Язык", "🌐 Language"):
        with db() as con:
            new_lang = "en" if get_lang(uid) == "ru" else "ru"
            con.execute("UPDATE users SET lang=? WHERE user_id=?", (new_lang, uid))
        return await message.answer("Language changed." if new_lang == "en" else "Язык изменён.", reply_markup=main_menu(uid))
    await message.answer(t(uid, "unknown"), reply_markup=main_menu(uid))


@dp.callback_query(F.data.startswith("add:"))
async def add_to_cart(call: CallbackQuery):
    uid = call.from_user.id
    pid = int(call.data.split(":")[1])
    with db() as con:
        exists = con.execute("SELECT id FROM products WHERE id=? AND active=1", (pid,)).fetchone()
        if exists:
            con.execute("""INSERT INTO cart(user_id,product_id,qty) VALUES(?,?,1)
                ON CONFLICT(user_id,product_id) DO UPDATE SET qty=qty+1""", (uid, pid))
    await call.answer(t(uid, "added"), show_alert=False)


@dp.callback_query(F.data.startswith("remove:"))
async def remove_from_cart(call: CallbackQuery):
    uid = call.from_user.id
    pid = int(call.data.split(":")[1])
    with db() as con:
        row = con.execute("SELECT qty FROM cart WHERE user_id=? AND product_id=?", (uid, pid)).fetchone()
        if row:
            if row["qty"] > 1:
                con.execute("UPDATE cart SET qty=qty-1 WHERE user_id=? AND product_id=?", (uid, pid))
            else:
                con.execute("DELETE FROM cart WHERE user_id=? AND product_id=?", (uid, pid))
    await call.answer()
    await call.message.delete()
    await show_cart(call.message, uid)


@dp.callback_query(F.data == "clearcart")
async def clear_cart(call: CallbackQuery):
    with db() as con:
        con.execute("DELETE FROM cart WHERE user_id=?", (call.from_user.id,))
    await call.answer(t(call.from_user.id, "deleted"))
    await call.message.edit_text(t(call.from_user.id, "deleted"))


@dp.callback_query(F.data == "checkout")
async def checkout(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    with db() as con:
        count = con.execute("SELECT COUNT(*) n FROM cart WHERE user_id=?", (uid,)).fetchone()["n"]
    if not count:
        return await call.answer(t(uid, "empty"), show_alert=True)
    await state.set_state(Checkout.name)
    await call.message.answer(t(uid, "name"))
    await call.answer()


@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.answer(t(call.from_user.id, "welcome", shop=SHOP_NAME), reply_markup=main_menu(call.from_user.id))
    await call.answer()


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
