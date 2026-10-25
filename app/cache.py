import time
from typing import Any, Awaitable, Callable

_STORE: dict[str, tuple[float, Any]] = {}


async def cached(key: str, ttl: int, loader: Callable[[], Awaitable[Any]]):
    """Renvoie la valeur en cache si elle est récente, sinon la recharge.
    En cas d'erreur réseau, une ancienne valeur (même périmée) est préférée à une panne."""
    now = time.time()
    hit = _STORE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        value = await loader()
    except Exception:
        if hit:
            return hit[1]
        raise
    _STORE[key] = (now, value)
    return value
