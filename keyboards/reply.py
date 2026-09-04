"""
Reply (pastdagi) klaviaturalar — ko'p tillilik (uz/ru/en) bilan
"""
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from config import settings
from i18n import t


def main_reply_keyboard(lang: str = "uz") -> ReplyKeyboardMarkup:
    """Asosiy reply klaviatura — inline menyu bilan bir xil tugmalar."""
    builder = ReplyKeyboardBuilder()

    # 1-qator: Mini App — plain text (bot token generatsiya qiladi)
    builder.row(KeyboardButton(text=t("kb.app", lang)))

    # 2-qator: Yangi vazifa | Mening vazifalarim
    builder.row(
        KeyboardButton(text=t("kb.newtask", lang)),
        KeyboardButton(text=t("kb.mytasks", lang)),
    )

    # 3-qator: Statistika | Kechikganlar
    builder.row(
        KeyboardButton(text=t("kb.stats", lang)),
        KeyboardButton(text=t("kb.overdue", lang)),
    )

    # 4-qator: Jamoalarim | Guruhlarim
    builder.row(
        KeyboardButton(text=t("kb.companies", lang)),
        KeyboardButton(text=t("kb.groups", lang)),
    )

    # 5-qator: Murojaat | Sozlamalar
    builder.row(
        KeyboardButton(text=t("kb.feedback", lang)),
        KeyboardButton(text=t("kb.settings", lang)),
    )

    return builder.as_markup(
        resize_keyboard=True,
        input_field_placeholder=t("kb.placeholder", lang),
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    """Klaviaturani olib tashlash"""
    return ReplyKeyboardRemove()


def contact_keyboard() -> ReplyKeyboardMarkup:
    """Kontakt yuborish uchun"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Kontaktni ulashish", request_contact=True)
    builder.button(text="❌ Bekor qilish")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
