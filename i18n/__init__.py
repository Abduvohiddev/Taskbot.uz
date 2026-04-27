"""
i18n - Internationalization module
Quick translation lookup with fallback to Uzbek (default).
Usage:
    from i18n import t
    text = t("settings.title", lang="ru")
"""
from typing import Any
from .locales import TRANSLATIONS

DEFAULT_LANG = "uz"
SUPPORTED_LANGS = ("uz", "ru", "en")


def t(key: str, lang: str = DEFAULT_LANG, /, **kwargs: Any) -> str:
    """Translate a key into the target language.

    `lang` is positional-only (note the `/`) so kwargs may contain a `lang`
    key for str.format() interpolation without collision.

    Falls back to Uzbek if key missing in target language.
    Falls back to the key itself if missing everywhere.
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG

    bundle = TRANSLATIONS.get(lang, {})
    text = bundle.get(key)
    if text is None:
        text = TRANSLATIONS.get(DEFAULT_LANG, {}).get(key, key)

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def get_all(lang: str = DEFAULT_LANG) -> dict:
    """Return the entire translation dict for a language (for mini app)."""
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    # Merge with default for missing keys
    base = dict(TRANSLATIONS.get(DEFAULT_LANG, {}))
    base.update(TRANSLATIONS.get(lang, {}))
    return base
