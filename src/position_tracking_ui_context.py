"""Explicit runtime providers supplied by the application composition boundary."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class WindowServices:
    config_type: type
    app_dir: Callable[[], Path]
    local_root: Callable[[], Path]
    machine_queue_root: Callable[[], Path]
    open_path: Callable
