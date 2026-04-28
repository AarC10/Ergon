from slugify import slugify as _slugify


def slugify(text: str, max_length: int = 60) -> str:
    return _slugify(text, max_length=max_length, word_boundary=True, save_order=True)
