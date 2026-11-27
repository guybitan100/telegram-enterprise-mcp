from aiogram.types import Message

from .config import ADMIN_ID


def is_admin_private(message: Message) -> bool:
    """Allow administrative actions only for the configured user in private chat."""
    return message.from_user.id == ADMIN_ID and message.chat.type == "private"
