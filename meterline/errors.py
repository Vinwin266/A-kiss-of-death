"""The exception hierarchy used throughout the engine.

Every error raised on purpose derives from :class:`MeterlineError`, so an
embedding application can distinguish "the engine said no" from "the engine
has a bug".  Errors carry a short stable ``code`` in addition to their
message: codes are part of the public surface and are safe to branch on,
messages are not.
"""

from __future__ import annotations

from typing import Any, Mapping


class MeterlineError(Exception):
    """Base class for every error the engine raises deliberately."""

    code = "meterline.error"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __str__(self) -> str:  # pragma: no cover - trivial
        if not self.context:
            return self.message
        rendered = ", ".join(
            f"{key}={self.context[key]!r}" for key in sorted(self.context)
        )
        return f"{self.message} ({rendered})"

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly description of the error."""

        return {
            "code": self.code,
            "message": self.message,
            "context": {key: str(value) for key, value in sorted(self.context.items())},
        }


class ConfigurationError(MeterlineError):
    """Raised when the engine is wired up in a way that cannot work."""

    code = "meterline.configuration"


class DatasetError(MeterlineError):
    """Raised when a dataset file is structurally unusable."""

    code = "meterline.dataset"


class SchemaError(DatasetError):
    """Raised when a decoded document does not match the expected schema."""

    code = "meterline.schema"


class UnknownReferenceError(DatasetError):
    """Raised when a record points at an identifier that does not exist."""

    code = "meterline.unknown_reference"


class TariffError(MeterlineError):
    """Raised when a tariff is internally inconsistent."""

    code = "meterline.tariff"


class UnknownComponentError(TariffError):
    """Raised when a tariff names a component kind the catalog cannot build."""

    code = "meterline.tariff.unknown_component"


class RatingError(MeterlineError):
    """Raised when a bill cannot be produced from otherwise valid inputs."""

    code = "meterline.rating"


class MeterDataError(MeterlineError):
    """Raised when meter data cannot be turned into billing determinants."""

    code = "meterline.meterdata"


class QuantityError(MeterlineError):
    """Raised on an arithmetic mistake between incompatible quantities."""

    code = "meterline.quantity"


class CurrencyMismatch(MeterlineError):
    """Raised when two amounts in different currencies are combined."""

    code = "meterline.currency_mismatch"


class UnitMismatch(QuantityError):
    """Raised when two quantities in incompatible units are combined."""

    code = "meterline.unit_mismatch"


class PolicyError(MeterlineError):
    """Raised when a policy profile asks for something contradictory."""

    code = "meterline.policy"


class TimelineError(MeterlineError):
    """Raised for impossible spans, cycles and calendar requests."""

    code = "meterline.timeline"


def require(condition: bool, message: str, /, **context: Any) -> None:
    """Raise :class:`ConfigurationError` when ``condition`` is false."""

    if not condition:
        raise ConfigurationError(message, **context)


def reference(mapping: Mapping[str, Any], key: str, *, kind: str) -> Any:
    """Look ``key`` up in ``mapping`` or raise :class:`UnknownReferenceError`."""

    try:
        return mapping[key]
    except KeyError:
        raise UnknownReferenceError(
            f"no such {kind}", kind=kind, identifier=key
        ) from None
