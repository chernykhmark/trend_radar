from src.sources.base import BaseSource
from src.sources.habr import HabrSource

SOURCE_TYPES: dict[str, type[BaseSource]] = {
    "habr": HabrSource,
}


def build_source(config: dict) -> BaseSource:
    """
    config = {"name": "...", "type": "habr", "enabled": true, "params": {...}}
    """
    type_ = config["type"]
    if type_ not in SOURCE_TYPES:
        raise ValueError(f"Unknown source type: {type_}")
    cls = SOURCE_TYPES[type_]
    return cls(name=config["name"], params=config.get("params", {}) or {})