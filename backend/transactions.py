"""Serialize commerce mutations within Nova's single-process JSON deployment."""

from functools import wraps
from threading import RLock

commerce_lock = RLock()


def serialized(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with commerce_lock:
            return function(*args, **kwargs)
    return wrapper
