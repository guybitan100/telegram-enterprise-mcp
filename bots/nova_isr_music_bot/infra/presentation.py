def display_title(title: str) -> str:
    """Format a normalized catalog title for user-facing menus."""
    return title.title()


def id_from_callback(data: str, prefix: str) -> int | None:
    """Parse a numeric callback ID only when the expected prefix is present."""
    try:
        if not data.startswith(prefix):
            return None
        return int(data[len(prefix) :])
    except ValueError:
        return None
