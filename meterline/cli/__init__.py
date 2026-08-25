"""The command line interface.

The CLI is a thin shell over :class:`~meterline.session.Session`.  Every
command loads a dataset, asks the engine something and renders the answer;
none of them compute anything the library cannot.  That constraint is what
keeps ``meterline rate`` and an embedding application from drifting apart.
"""

from __future__ import annotations

from .app import main, run

__all__ = ["main", "run"]
