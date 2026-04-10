import functools
import logging
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def authorized(user_id: int) -> Callable:
    """Decorator that silently ignores updates from unauthorized users."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            effective_user = update.effective_user
            if not effective_user or effective_user.id != user_id:
                logger.warning("Unauthorized access from user %s", effective_user)
                return
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
