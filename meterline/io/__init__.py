"""Reading and writing datasets.

The only part of the engine allowed to touch a file.  Everything the loader
produces is a plain in-memory :class:`~meterline.dataset.Dataset`, so a
caller that builds one itself gets exactly the same behaviour as one that
reads it from disk — which is what makes the test suite able to avoid
fixtures without diverging from the real path.
"""

from __future__ import annotations

from .decode import dataset_from_dict
from .encode import dataset_to_dict, invoice_to_dict
from .files import load_dataset, read_json, write_json, write_text
from .jsonio import canonical_dumps, canonical_loads
from .schema import Field, require_keys, take_list, take_str

__all__ = [
    "Field",
    "canonical_dumps",
    "canonical_loads",
    "dataset_from_dict",
    "dataset_to_dict",
    "invoice_to_dict",
    "load_dataset",
    "read_json",
    "require_keys",
    "take_list",
    "take_str",
    "write_json",
    "write_text",
]
