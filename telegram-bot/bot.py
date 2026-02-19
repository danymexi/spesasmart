"""SpesaSmart Telegram Bot for notifications and product search."""

import logging
import os

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - register user."""
    chat_id = update.effective_chat.id
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE_URL}/users",
            json={"telegram_chat_id": chat_id},
        )
        if resp.status_code == 201:
            user = resp.json()
            await update.message.reply_text(
                f"Benvenuto su SpesaSmart! 🛒\n\n"
                f"Il tuo ID utente: {user['id']}\n\n"
                f"Comandi disponibili:\n"
                f"/cerca <prodotto> - Cerca un prodotto\n"
                f"/offerte - Migliori offerte di oggi\n"
                f"/lista - La tua lista prodotti\n"
                f"/help - Aiuto"
            )
        else:
            await update.message.reply_text(
                "Benvenuto! Usa /cerca per cercare prodotti in offerta."
            )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cerca command - search products."""
    if not context.args:
        await update.message.reply_text("Uso: /cerca <nome prodotto>\nEsempio: /cerca latte granarolo")
        return

    query = " ".join(context.args)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/products/search",
            params={"q": query, "limit": 5},
        )
        if resp.status_code != 200:
            await update.message.reply_text("Errore nella ricerca. Riprova.")
            return

        results = resp.json()
        if not results:
            await update.message.reply_text(f"Nessun prodotto trovato per '{query}'.")
            return

        text = f"🔍 Risultati per '{query}':\n\n"
        for r in results:
            product = r["product"]
            price_text = ""
            if r.get("best_current_price"):
                price_text = f" - €{r['best_current_price']} ({r.get('chain_name', '')})"
            text += f"• {product['name']}"
            if product.get("brand"):
                text += f" ({product['brand']})"
            text += f"{price_text}\n"

        await update.message.reply_text(text)


async def offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /offerte command - show best current offers."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE_URL}/offers/best",
            params={"limit": 10},
        )
        if resp.status_code != 200:
            await update.message.reply_text("Errore nel caricamento offerte.")
            return

        offers_list = resp.json()
        if not offers_list:
            await update.message.reply_text("Nessuna offerta attiva al momento.")
            return

        text = "🔥 Migliori offerte di oggi:\n\n"
        for o in offers_list:
            discount = ""
            if o.get("discount_pct"):
                discount = f" (-{o['discount_pct']}%)"
            text += (
                f"• {o['product_name']} - €{o['offer_price']}{discount}\n"
                f"  📍 {o['chain_name']}"
            )
            if o.get("original_price"):
                text += f" (era €{o['original_price']})"
            text += "\n\n"

        await update.message.reply_text(text)


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /lista command - show user watchlist."""
    # For simplicity, use chat_id to find user
    await update.message.reply_text(
        "Per gestire la tua lista prodotti, usa l'app SpesaSmart.\n"
        "Riceverai notifiche qui quando i tuoi prodotti saranno in offerta!"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "🛒 SpesaSmart Bot - Confronta prezzi supermercati\n\n"
        "Comandi:\n"
        "/cerca <prodotto> - Cerca prodotti e prezzi\n"
        "/offerte - Migliori offerte attive\n"
        "/lista - La tua lista prodotti\n"
        "/help - Questo messaggio\n\n"
        "Supermercati monitorati:\n"
        "• Esselunga\n"
        "• Lidl\n"
        "• Coop\n"
        "• Iperal\n\n"
        "Zona: Monza e Brianza"
    )


def main():
    """Start the Telegram bot."""
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cerca", search))
    app.add_handler(CommandHandler("offerte", offers))
    app.add_handler(CommandHandler("lista", watchlist))
    app.add_handler(CommandHandler("help", help_command))

    logger.info("SpesaSmart Telegram bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
