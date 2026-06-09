"""Live data sources. Each module exposes a ``fetch(...)`` returning a plain
dict and is independently replaceable, so the engine can be fortified (or merged
with another repo) one source at a time."""
