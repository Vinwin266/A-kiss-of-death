"""Reading and writing files.

Every path the engine touches goes through here so that a run's file access
is auditable in one place, and so that the error a missing dataset produces
mentions the path rather than surfacing a bare ``FileNotFoundError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dataset import Dataset
from ..errors import DatasetError
from .decode import dataset_from_dict
from .jsonio import canonical_dumps, canonical_loads

__all__ = ["read_text", "write_text", "read_json", "write_json", "load_dataset"]


def read_text(path: str | Path) -> str:
    """Return the contents of a UTF-8 text file."""

    target = Path(path)
    try:
        return target.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise DatasetError("file not found", path=str(target)) from None
    except IsADirectoryError:
        raise DatasetError("expected a file, found a directory", path=str(target)) from None
    except UnicodeDecodeError:
        raise DatasetError("file is not valid UTF-8", path=str(target)) from None


def write_text(path: str | Path, content: str) -> Path:
    """Write text to a file, creating parent directories as needed."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def read_json(path: str | Path) -> Any:
    """Read and parse a JSON file."""

    return canonical_loads(read_text(path), what=str(path))


def write_json(path: str | Path, document: Any, *, indent: int = 2) -> Path:
    """Write a document as canonical JSON."""

    return write_text(path, canonical_dumps(document, indent=indent))


def load_dataset(path: str | Path) -> Dataset:
    """Read a dataset file and build the in-memory dataset."""

    document = read_json(path)
    dataset = dataset_from_dict(document)
    if dataset.name == "dataset":
        dataset.name = Path(path).stem
    return dataset
