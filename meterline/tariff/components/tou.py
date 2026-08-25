"""Time-of-use energy charges."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from ...charge.classes import ChargeClass, ChargeSide
from ...charge.context import RatingContext
from ...charge.lineitem import LineItem, LineItemBuilder
from ...core.decimals import D, is_zero
from ...core.units import Unit
from ...errors import TariffError
from ...model.quality import QualityCode
from .base import Component, Stage

__all__ = ["TouCharge"]


class TouCharge(Component):
    """Prices per-bucket energy determinants at per-bucket rates.

    The component does not decide which hours are peak — that is the window
    set's job, applied when determinants were derived.  It only prices what
    it is given, which is why a tariff can change its window definitions
    without touching its rates.
    """

    kind = "tou"

    def __init__(
        self,
        code: str,
        label: str,
        rates: Mapping[str, Decimal | str],
        *,
        prefix: str = "energy.bucket",
        unit: Unit = Unit.KWH,
        side: ChargeSide = ChargeSide.SUPPLY,
        stage: int = Stage.ENERGY,
        charge_class: ChargeClass = ChargeClass.ENERGY,
        require_all: bool = False,
    ) -> None:
        super().__init__(code, label, charge_class, stage, side)
        if not rates:
            raise TariffError("a time-of-use charge needs at least one rate", component=code)
        self.rates = {bucket: D(rate) for bucket, rate in rates.items()}
        self.prefix = prefix
        self.unit = unit
        self.require_all = require_all
        """When true, a missing bucket determinant is an error, not a zero."""

    def determinants(self) -> tuple[str, ...]:
        """Return the per-bucket determinant names this component reads."""

        return tuple(f"{self.prefix}.{bucket}" for bucket in sorted(self.rates))

    def compute(
        self, context: RatingContext, so_far: Sequence[LineItem]
    ) -> list[LineItem]:
        """Return one line per bucket that carried usage."""

        lines: list[LineItem] = []
        for bucket in sorted(self.rates):
            name = f"{self.prefix}.{bucket}"
            if self.require_all:
                determinant = context.determinants.require(
                    name, why=f"{self.code} prices the {bucket} bucket"
                )
                measured = determinant.quantity.to(self.unit)
                quality = determinant.quality
            else:
                found = context.determinants.get(name)
                if found is None:
                    context.notice(
                        "tariff.tou.missing_bucket",
                        "no usage was recorded in this time-of-use bucket",
                        bucket=bucket,
                        component=self.code,
                    )
                    continue
                measured = found.quantity.to(self.unit)
                quality = found.quality
            if is_zero(measured.value):
                continue
            rate = self.rates[bucket]
            builder = LineItemBuilder(
                f"{self.code}.{bucket}",
                f"{self.label} — {bucket}",
                self.charge_class,
                self.code,
                self.side,
            )
            builder.measure(measured, f"{bucket} usage")
            builder.priced_at(rate, f"{bucket} rate")
            builder.flag(quality if quality is not QualityCode.VALID else QualityCode.VALID)
            builder.detail(bucket=bucket, determinant=name)
            lines.append(builder.seal(context.money(measured.value * rate)))
        return lines

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON friendly view of the component."""

        data = super().as_dict()
        data.update(
            {
                "prefix": self.prefix,
                "unit": str(self.unit),
                "require_all": self.require_all,
                "rates": {bucket: str(rate) for bucket, rate in sorted(self.rates.items())},
            }
        )
        return data

    def describe(self) -> str:
        """Return a multi-line description for reports."""

        head = f"{self.code}: {self.label} (time of use)"
        body = "\n".join(
            f"    {bucket}: {self.rates[bucket]} per {self.unit}"
            for bucket in sorted(self.rates)
        )
        return f"{head}\n{body}"
