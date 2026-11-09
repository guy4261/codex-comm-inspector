"""Local text estimates shared by the timeline and trace analysis."""

from functools import lru_cache


@lru_cache(maxsize=64)
def tokenizer(model):
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("o200k_base")


def token_counter(model):
    try:
        encoding = tokenizer(model if isinstance(model, str) else "")
    except (ImportError, OSError, ValueError, RuntimeError):
        return "Unicode characters", None
    return encoding.name, lambda text: len(encoding.encode_ordinary(text))
