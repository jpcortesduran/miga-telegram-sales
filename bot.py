


import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta

from warnings import filterwarnings
import logging
from pathlib import Path
import shutil
import json

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.warnings import PTBUserWarning

from prettytable import PrettyTable
from tabulate import tabulate


logging.basicConfig( format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)


# Stages
MAIN_STAGE = 0

# Callback data
MAIN_MENU = 0
PRODUCTS, ADD_PRODUCT, MODIFY_PRODUCT, DELETE_PRODUCT = range(100, 104)
PAYMENTS, ADD_PAYMENT, MODIFY_PAYMENT, DELETE_PAYMENT = range(200, 204)
SALE, SALE_SELECT_PRODUCT, SALE_SELECT_QTY, SALE_MANUAL_QTY, SALE_ADD_BASE, SALE_MODIFY_PRICE, SALE_ADD_MANUAL, SALE_VIEW_CART, SALE_ADD_ANOTHER, SALE_CANCEL, SALE_CONFIRM, SALE_SELECT_PAYMENT, SALE_FINALIZE = range(300, 313)


TOKEN = "8468595929:AAGhUC4Xg42EJ5eRylxFAj4rV2XXGzbhiTM"

PRODUCTS_DATA_FILE = Path("custom_products_data.json")
PRODUCTS_DEFAULT_FILE = Path("default_products_data.json")

PAYMENTS_DATA_FILE = Path("custom_payments_data.json")
PAYMENTS_DEFAULT_FILE = Path("default_payments_data.json")



def format_cop(price: int) -> str:
    return f"${price:,.0f}".replace(",", ".")


def clear_context_userdata(context: ContextTypes.DEFAULT_TYPE, keys):
    for k in keys: context.user_data.pop(k, None)


class bot:


    def __init__(self):
        self.product_data = self.load_data(PRODUCTS_DEFAULT_FILE, PRODUCTS_DATA_FILE)
        self.payment_data = self.load_data(PAYMENTS_DEFAULT_FILE, PAYMENTS_DATA_FILE)
        self.gs_client = self.init_gsheets()
        print(self.gs_client.openall())
        self.sheet = self.gs_client.open("Contabilidad MIGA").worksheet("Ventas Telegram")

    def init_gsheets(self):
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        return gspread.authorize(creds)

    def load_data(self, default_file:Path, data_file:Path):
        if not data_file.exists():
            shutil.copy(default_file, data_file)

        with data_file.open(encoding="utf-8") as f:
            return json.load(f)

    def save_data(self, data:json, data_file:Path):
        with data_file.open( 'w', encoding="utf-8") as f:
            json.dump(data, f, indent=3)


    def build_products_table(self) -> str:

        name_width = max(len(name) for name in self.product_data.keys())

        empty_line = " " * (name_width) + "  |  "

        lines = [
            f"{'Nombre'.ljust(name_width)}  |  Precio",
            empty_line,
            "─" * (name_width + 15),
        ]

        for name, price in sorted(self.product_data.items(), key=lambda x: (x[0], x[1])):
            price_str = f"${price:,.0f}".replace(",", ".")
            lines.append(empty_line)
            lines.append(f"{name.ljust(name_width)}  |  {price_str}")

        return "\n".join(lines)
    

    def build_payment_methods_table(self) -> str:

        name_width = max(len(name) for name in self.payment_data)

        lines = [
            f"{'Nombre'.ljust(name_width)}\n",
            "─" * (name_width + 4),
        ]

        for name in sorted(self.payment_data):
            lines.append("")
            lines.append(f"{name.ljust(name_width)}")

        return "\n".join(lines)
    
    def render_cart_text(self, cart) -> tuple[str, int]:
    
        lines = ["🛒 <b>Carrito actual:</b>\n"]
        table = []
        headers = ["Producto", "Cant.", "Precio", "Total"]
        total = 0
        for item in cart: 
            lt = item["qty"] * item["final_price"]
            total += lt 
            table.append([item['product_name'], item['qty'], format_cop(item['final_price']), format_cop(lt)]) 
            
        lines.append(f'<pre>{tabulate(table, headers, tablefmt="presto")}\n</pre>')
        lines.append(f"<b>Total:</b> {format_cop(total)}")
        return "\n".join(lines), total


    async def render_main(self, chat, edit_message=None):
        keyboard = [
            [InlineKeyboardButton("Registrar Venta", callback_data=str(SALE))],
            [InlineKeyboardButton("⚙️ Administrar Productos", callback_data=str(PRODUCTS))],
            [InlineKeyboardButton("⚙️ Administrar Medios de Pago", callback_data=str(PAYMENTS))],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if edit_message:
            await edit_message.edit_message_text("🏠 <b>Ventas MIGA</b> - Menú Principal", reply_markup=reply_markup, parse_mode="HTML")
        else:
            await chat.send_message("🏠 <b>Ventas MIGA</b> - Menú Principal", reply_markup=reply_markup, parse_mode="HTML")


    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

        query = update.callback_query

        if query:
            await query.answer()
            await self.render_main(None, query)
        
        else:
            user = update.message.from_user
            logger.info("User %s started the conversation.", user.first_name)
            await self.render_main(update.effective_chat)

        return MAIN_STAGE
    

    async def products(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

        keyboard = [
            [InlineKeyboardButton("➕ Agregar", callback_data=str(ADD_PRODUCT))],
            [InlineKeyboardButton("✏️ Modificar", callback_data=str(MODIFY_PRODUCT))],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        prods_str = self.build_products_table()

        query = update.callback_query

        if query:
            await query.answer()
            await query.edit_message_text(
                f'<b>Sabores Registrados:</b>\n\n<pre>{prods_str}\n</pre>\n',
                parse_mode="HTML", 
                reply_markup=reply_markup 
            )

        else:
            await update.message.reply_text(
                f'<b>Sabores Registrados:</b>\n\n<pre>{prods_str}\n</pre>\n',
                parse_mode="HTML", 
                reply_markup=reply_markup 
            )

        return MAIN_STAGE


    async def add_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["adding_product_name"] = True
        context.user_data["adding_product_price"] = False
        await query.edit_message_text( "Ingrese el nombre del nuevo producto:")
        
        return MAIN_STAGE
    

    async def modify_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["product_map"] = list(sorted(self.product_data.keys()))
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"mod_prod:{idx}")]
            for idx, name in enumerate(context.user_data["product_map"])
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Regresar", callback_data=str(PRODUCTS))])
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Seleccione el producto que desea modificar:", reply_markup=reply_markup)
        
        return MAIN_STAGE


    async def modify_product_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["modifying_product"] = int(query.data.split(":")[1])
        name = context.user_data["product_map"][context.user_data["modifying_product"]]

        price_str = f"${self.product_data[name]:,.0f}".replace(",", ".")
        
        keyboard = [
            [InlineKeyboardButton(button_name, callback_data=f"mod_opt_{button_name}")]
            for button_name in ['Modificar Nombre', 'Modificar Precio', 'Eliminar']
        ]
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Modificando:\n'{name}' (Precio: {price_str})\n", reply_markup=reply_markup)
        
        return MAIN_STAGE
    

    async def modify_product_specific(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        name = context.user_data["product_map"][context.user_data["modifying_product"]]
        context.user_data["modifying_product_name"] = False
        context.user_data["modifying_product_price"] = False
        button_type = query.data[8:]

        if button_type == 'Modificar Nombre':
            context.user_data["modifying_product_name"] = True
            await query.edit_message_text( f"Ingrese el nuevo NOMBRE para el producto '{name}':")
        
        elif button_type == 'Modificar Precio':
            context.user_data["modifying_product_price"] = True
            await query.edit_message_text( f"Ingrese el nuevo PRECIO para el producto '{name}':")
        
        elif button_type == 'Eliminar':
            
            keyboard = [
                [InlineKeyboardButton("Sí, eliminar", callback_data=str(DELETE_PRODUCT))],
                [InlineKeyboardButton("⬅️ Regresar", callback_data=f"mod_prod:{context.user_data['modifying_product']}")]
            ]
            keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"¿Está seguro de eliminar el producto '{name}'?", reply_markup=reply_markup)
        
        return MAIN_STAGE
    
    async def delete_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        name = context.user_data["product_map"][context.user_data["modifying_product"]]
        if name in self.product_data:
            del self.product_data[name]
            self.save_data(self.product_data, PRODUCTS_DATA_FILE)
            clear_context_userdata(context, ["modifying_product", "modifying_product_name", "modifying_product_price", "product_map"] )
            await query.edit_message_text(f"✅ Producto '{name}' eliminado.")
            return await self.products(update, context)



    async def payment_methods(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

        keyboard = [
            [InlineKeyboardButton("➕ Agregar", callback_data=str(ADD_PAYMENT))],
            [InlineKeyboardButton("✏️ Modificar", callback_data=str(MODIFY_PAYMENT))],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        prods_str = self.build_payment_methods_table()

        query = update.callback_query

        if query:
            await query.answer()
            await query.edit_message_text(
                f'<b>Métodos de Pago:</b>\n\n<pre>{prods_str}\n</pre>\n',
                parse_mode="HTML", 
                reply_markup=reply_markup 
            )

        else:
            await update.message.reply_text(
                f'<b>Métodos de Pago:</b>\n\n<pre>{prods_str}\n</pre>\n',
                parse_mode="HTML", 
                reply_markup=reply_markup 
            )

        return MAIN_STAGE


    async def add_payment_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        context.user_data["adding_payment_method"] = True
        await query.edit_message_text( "Ingrese el nombre del nuevo Método de Pago:")
        return MAIN_STAGE
    

    async def modify_payment_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["payment_method_map"] = list(sorted(self.payment_data))
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"mod_paym:{idx}")]
            for idx, name in enumerate(context.user_data["payment_method_map"])
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Regresar", callback_data=str(PAYMENTS))])
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Seleccione el Método de Pago que desea modificar:", reply_markup=reply_markup)
        
        return MAIN_STAGE
    
    async def modify_payment_method_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["modifying_payment"] = int(query.data.split(":")[1])
        name = context.user_data["payment_method_map"][context.user_data["modifying_payment"]]
        
        keyboard = [
            [InlineKeyboardButton(button_name, callback_data=f"mod_paymopt_{button_name}")]
            for button_name in ['Eliminar']
        ]
        keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Modificando el método de pago:\n'{name}'\n", reply_markup=reply_markup)
        
        return MAIN_STAGE
    
    async def modify_payment_method_specific(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        name = context.user_data["payment_method_map"][context.user_data["modifying_payment"]]
        button_type = query.data[12:]
        
        if button_type == 'Eliminar':
            
            keyboard = [
                [InlineKeyboardButton("Sí, eliminar", callback_data=str(DELETE_PAYMENT))],
                [InlineKeyboardButton("⬅️ Regresar", callback_data=f'mod_paym:{context.user_data["modifying_payment"]}')]
            ]
            keyboard.append([InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"¿Está seguro de eliminar el método de pago '{name}'?", reply_markup=reply_markup)
        
        return MAIN_STAGE
    
    async def delete_payment_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        name = context.user_data["payment_method_map"][context.user_data["modifying_payment"]]
        if name in self.payment_data:
            self.payment_data.remove(name)
            self.save_data(self.payment_data, PAYMENTS_DATA_FILE)
            clear_context_userdata(context, ["modifying_payment", "payment_method_map"] )
            await query.edit_message_text(f"✅ Método de pago '{name}' eliminado.")
            return await self.payment_methods(update, context)


    async def sale(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

        query = update.callback_query
        await query.answer()
        
        if "cart" not in context.user_data:
            context.user_data["cart"] = []

        context.user_data.pop("sale_current_product", None)
        context.user_data.pop("sale_qty", None)
        context.user_data.pop("sale_base_price", None)
        context.user_data.pop("sale_final_price", None)

        return await self.sale_view_cart(update, context)


    async def sale_select_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"sale_prod:{idx}")]
            for idx, name in enumerate(sorted(self.product_data))
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Regresar", callback_data=str(SALE_VIEW_CART))])

        reply_markup = InlineKeyboardMarkup(keyboard)

        query = update.callback_query
        await query.edit_message_text("Seleccione el producto:", reply_markup=reply_markup)

        context.user_data["sale_product_map"] = list(sorted(self.product_data))
        return MAIN_STAGE


    async def sale_select_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        idx = int(query.data.split(":")[1])
        name = context.user_data["sale_product_map"][idx]

        context.user_data["sale_current_product"] = name
        context.user_data["sale_base_price"] = self.product_data[name]
        context.user_data["sale_final_price"] = self.product_data[name]

        keyboard = [
            [
                InlineKeyboardButton("1️⃣", callback_data="sale_qty:1"),
                InlineKeyboardButton("2️⃣", callback_data="sale_qty:2"),
                InlineKeyboardButton("3️⃣", callback_data="sale_qty:3"),
                InlineKeyboardButton("4️⃣", callback_data="sale_qty:4"),
                InlineKeyboardButton("5️⃣", callback_data="sale_qty:5"),
            ],
            [InlineKeyboardButton("✏️ Otra Cantidad", callback_data=str(SALE_MANUAL_QTY))],
            [InlineKeyboardButton("⬅️ Regresar", callback_data=str(SALE))],
        ]

        price_str = format_cop(context.user_data["sale_base_price"])

        await query.edit_message_text(
            f"Producto: <b>{name}</b>\n"
            f"Precio base x und: <b>{price_str}</b>\n\n"
            "Seleccione la cantidad:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

        return MAIN_STAGE
    
    async def sale_manual_qty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["awaiting_manual_qty"] = True

        await query.edit_message_text(
            "Ingrese la cantidad a vender (número entero mayor que 0):"
        )

        return MAIN_STAGE


    async def sale_price_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        

        name = context.user_data["sale_current_product"]
        base_price = context.user_data["sale_base_price"]
        final_price = context.user_data["sale_final_price"]

        keyboard = [
            [InlineKeyboardButton(f"✅ Agregar", callback_data=str(SALE_ADD_BASE))],
            [InlineKeyboardButton("✏️ Modificar precio x Und", callback_data=str(SALE_MODIFY_PRICE))],
            [InlineKeyboardButton("⬅️ Regresar", callback_data=f"sale_prod:{context.user_data['sale_product_map'].index(name)}")],
        ]

        query = update.callback_query

        if query:
            await query.answer()
            qty = int(query.data.split(":")[1])
            context.user_data["sale_qty"] = qty

            await query.edit_message_text(
                f"Producto: <b>{name}</b>\n"
                f"Cantidad: <b>{qty}</b>\n"
                f"Precio base x und: <b>{format_cop(base_price)}</b>\n"
                f"Precio actual x und: <b>{format_cop(final_price)}</b>\n\n"
                f"Total: <b>{format_cop(final_price * qty)}</b>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
        else:
            qty = context.user_data["sale_qty"]

            await update.message.reply_text(
                f"Producto: <b>{name}</b>\n"
                f"Cantidad: <b>{qty}</b>\n"
                f"Precio base x und: <b>{format_cop(base_price)}</b>\n"
                f"Precio actual x und: <b>{format_cop(final_price)}</b>\n"
                f"Total: <b>{format_cop(final_price * qty)}</b>\n",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
        

        return MAIN_STAGE
    

    async def sale_add_base(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        item = {
            "product_name": context.user_data["sale_current_product"],
            "qty": context.user_data["sale_qty"],
            "base_price": context.user_data["sale_base_price"],
            "final_price": context.user_data["sale_final_price"],
        }

        context.user_data["cart"].append(item)

        return await self.sale_view_cart(update, context)
    

    async def sale_modify_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        context.user_data["awaiting_manual_price"] = True

        await query.edit_message_text(
            "Ingrese el precio unitario final (solo números, 0 permitido):"
        )

        return MAIN_STAGE

    
    async def sale_view_cart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        

        cart = context.user_data.get("cart", [])
        text, _ = self.render_cart_text(cart)

        keyboard = [
            [InlineKeyboardButton("➕ Agregar producto", callback_data=str(SALE_ADD_ANOTHER))],
            [InlineKeyboardButton("✅ Confirmar venta", callback_data=str(SALE_CONFIRM))],
            [InlineKeyboardButton("❌ Cancelar venta", callback_data=str(SALE_CANCEL))],
            [InlineKeyboardButton("🏠 Menú Principal", callback_data=str(MAIN_MENU))],
        ]

        query = update.callback_query

        if query:
            await query.answer()

            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )

        return MAIN_STAGE

    


    async def sale_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        clear_context_userdata(context, ["cart", "sale_current_product", "sale_qty", "sale_base_price", "sale_product_map", "sale_final_price"])
        await query.edit_message_text("❌ Venta cancelada.")

        return await self.main_menu(update, context)


    async def sale_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        cart = context.user_data.get("cart", [])
        if not cart:
            await query.edit_message_text("⚠️ El carrito está vacío.")
            return MAIN_STAGE
        
        text, _ = self.render_cart_text(cart)

        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"sale_pay:{idx}")]
            for idx, name in enumerate(self.payment_data)
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Regresar", callback_data=str(SALE_VIEW_CART))])

        context.user_data["payment_method_map"] = self.payment_data

        await query.edit_message_text(
            text + "\n\nSeleccione el método de pago:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

        return MAIN_STAGE
    
    

    async def sale_select_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        cart = context.user_data["cart"]
        text, _ = self.render_cart_text(cart)

        idx = int(query.data.split(":")[1])
        payment = context.user_data["payment_method_map"][idx]
        context.user_data["sale_payment_method"] = payment

        keyboard = [
            [InlineKeyboardButton("✅ Registrar venta", callback_data=str(SALE_FINALIZE))],
            [InlineKeyboardButton("⬅️ Regresar", callback_data=str(SALE_CONFIRM))],
        ]

        await query.edit_message_text(
            text + f"\n\nMétodo de pago seleccionado:\n<b>{payment}</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

        return MAIN_STAGE


    async def sale_finalize(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        cart = context.user_data["cart"]
        payment = context.user_data["sale_payment_method"]

        tz_co = timezone(timedelta(hours=-5))
        ts = datetime.now(timezone.utc).astimezone(tz_co).strftime("%Y-%m-%d %H:%M:%S")

        rows = []
        for item in cart:
            rows.append([
                ts,
                item["product_name"],
                item["qty"],
                item["base_price"],
                item["final_price"],
                item["qty"] * item["final_price"],
                payment,
            ])

        self.sheet.append_rows(rows, value_input_option="USER_ENTERED")

        text, total = self.render_cart_text(cart)
        final_text = (
            "✅ <b>Venta registrada exitosamente</b>\n\n"
            f"{text}\n\n"
            f"<b>Método de pago:</b> {payment}\n"
            f"<b>Fecha:</b> {ts}"
        ) 

        clear_context_userdata(context, ["cart", "sale_current_product", "sale_qty", "sale_base_price", "sale_product_map", "sale_final_price", "sale_payment_method"])
        await query.edit_message_text(final_text, parse_mode="HTML")

        await self.render_main(update.effective_chat)
        return MAIN_STAGE


    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

        if context.user_data:

            text = update.message.text.strip()

            if context.user_data.get("awaiting_manual_qty"):
                try:
                    qty = int(text)
                    if qty <= 0:
                        raise ValueError
                except ValueError:
                    await update.message.reply_text("Ingrese un número entero mayor que 0:")
                    return MAIN_STAGE

                context.user_data["sale_qty"] = qty
                context.user_data.pop("awaiting_manual_qty")

                return await self.sale_price_options(update, context)


            elif context.user_data.get("awaiting_manual_price"):
                try:
                    price = int(text)
                    if price < 0:
                        raise ValueError
                except ValueError:
                    await update.message.reply_text("Ingrese un número válido (0 o mayor):")
                    return MAIN_STAGE
                
                context.user_data["sale_final_price"] = price

                return await self.sale_price_options(update, context)
            
            elif context.user_data.get("adding_product_name"):

                if text in self.product_data:
                    await update.message.reply_text("⚠️ Ese producto ya existe. Intente nuevamente")
                    return MAIN_STAGE
                
                context.user_data["new_product_name"] = text
                context.user_data["adding_product_name"] = False
                context.user_data["adding_product_price"] = True

                await update.message.reply_text("Ingrese el precio del producto en COP (solo números):")
                return MAIN_STAGE
            
            elif context.user_data.get("adding_product_price"):
                try:
                    price = int(text)
                except ValueError:
                    await update.message.reply_text("Debe ser un número entero. Intente de nuevo:")
                    return MAIN_STAGE
                
                name = context.user_data["new_product_name"]
                self.product_data[name] = price
                self.save_data(self.product_data, PRODUCTS_DATA_FILE)

                clear_context_userdata(context, ['new_product_name', "adding_product_name",'adding_product_price'] )
                
                await update.message.reply_text(f"✅ Producto '{name}' agregado con precio {format_cop(price)} COP.")
                return await self.products(update, context)
            
            elif context.user_data.get("modifying_product"):
                
                if context.user_data["modifying_product_name"]:
                    old_name = context.user_data["product_map"][context.user_data["modifying_product"]]
                    old_p = self.product_data[old_name]
                    del self.product_data[old_name]
                    self.product_data[text] = old_p
                    await update.message.reply_text(f"✅ El nombre del producto '{old_name}' fue actualizado a '{text}'.")

                elif context.user_data["modifying_product_price"]:
                    try:
                        price = int(text)
                    except ValueError:
                        await update.message.reply_text("Debe ser un número entero. Intente de nuevo:")
                        return MAIN_STAGE
                    
                    name = context.user_data["product_map"][context.user_data["modifying_product"]]
                    old_p = self.product_data[name]
                    self.product_data[name] = price
                    await update.message.reply_text(f"✅ El precio del producto '{name}' fue actualizado {format_cop(old_p)} -> {format_cop(price)}.")

                self.save_data(self.product_data, PRODUCTS_DATA_FILE)
                clear_context_userdata(context, ['modifying_product', "modifying_product_name", "modifying_product_price", "product_map"] )
                return await self.products(update, context)

            elif context.user_data.get("adding_payment_method"):

                if text in self.payment_data:
                    await update.message.reply_text("⚠️ Ese método de pago ya existe. Intente nuevamente")
                    return MAIN_STAGE
                
                self.payment_data.append(text)
                self.save_data(self.payment_data, PAYMENTS_DATA_FILE)
                clear_context_userdata(context, ['adding_payment_method'] )

                await update.message.reply_text(f"✅ Se ha agregado el nuevo método de pago: '{text}'.")
                return await self.payment_methods(update, context)
    
        await self.render_main(update.effective_chat)
        return MAIN_STAGE


    def main(self) -> None:

        application = Application.builder().token(TOKEN).build()

        conv_handler = ConversationHandler( per_chat=True,
            entry_points=[CommandHandler("start", self.main_menu)],
            states={
                MAIN_STAGE: [
                    CallbackQueryHandler(self.main_menu, pattern="^" + str(MAIN_MENU) + "$"),
                    CallbackQueryHandler(self.products, pattern="^" + str(PRODUCTS) + "$"),
                    CallbackQueryHandler(self.add_product, pattern="^" + str(ADD_PRODUCT) + "$"),
                    CallbackQueryHandler(self.modify_product, pattern="^" + str(MODIFY_PRODUCT) + "$"),
                    CallbackQueryHandler(self.modify_product_options, pattern="^mod_prod:"),
                    CallbackQueryHandler(self.modify_product_specific, pattern="^mod_opt_"),
                    CallbackQueryHandler(self.delete_product, pattern="^" + str(DELETE_PRODUCT) + "$"),
                    CallbackQueryHandler(self.payment_methods, pattern="^" + str(PAYMENTS) + "$"),
                    CallbackQueryHandler(self.add_payment_method, pattern="^" + str(ADD_PAYMENT) + "$"),
                    CallbackQueryHandler(self.modify_payment_method, pattern="^" + str(MODIFY_PAYMENT) + "$"),
                    CallbackQueryHandler(self.modify_payment_method_options, pattern="^mod_paym:"),
                    CallbackQueryHandler(self.modify_payment_method_specific, pattern="^mod_paymopt_"),
                    CallbackQueryHandler(self.delete_payment_method, pattern="^" + str(DELETE_PAYMENT) + "$"),
                    CallbackQueryHandler(self.sale, pattern="^" + str(SALE) + "$"),
                    CallbackQueryHandler(self.sale_select_qty, pattern="^sale_prod:"),
                    CallbackQueryHandler(self.sale_manual_qty, pattern="^" + str(SALE_MANUAL_QTY) + "$"),
                    CallbackQueryHandler(self.sale_price_options, pattern="^sale_qty:"),
                    CallbackQueryHandler(self.sale_add_base, pattern="^" + str(SALE_ADD_BASE) + "$"),
                    CallbackQueryHandler(self.sale_modify_price, pattern="^" + str(SALE_MODIFY_PRICE) + "$"),
                    CallbackQueryHandler(self.sale_view_cart, pattern="^" + str(SALE_VIEW_CART) + "$"),
                    CallbackQueryHandler(self.sale_select_product, pattern="^" + str(SALE_ADD_ANOTHER) + "$"),
                    CallbackQueryHandler(self.sale_cancel, pattern="^" + str(SALE_CANCEL) + "$"),
                    CallbackQueryHandler(self.sale_confirm, pattern="^" + str(SALE_CONFIRM) + "$"),
                    CallbackQueryHandler(self.sale_select_payment, pattern="^sale_pay:"),
                    CallbackQueryHandler(self.sale_finalize, pattern="^" + str(SALE_FINALIZE) + "$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input),
                ],
            },
            fallbacks=[CommandHandler("start", self.main_menu)],
        )

        # Add ConversationHandler to application that will be used for handling updates
        application.add_handler(conv_handler)

        # Run the bot until the user presses Ctrl-C
        application.run_polling(allowed_updates=Update.ALL_TYPES)



if __name__ == "__main__":
    telbot = bot()
    telbot.main()

