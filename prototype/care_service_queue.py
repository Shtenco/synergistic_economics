"""Age-cohort queue for delayed, queueable household services."""
from __future__ import annotations

import math
from dataclasses import dataclass


EPS = 1e-9


class CareQueueError(ValueError):
    pass


@dataclass(frozen=True)
class CareQueueLot:
    quantity: float
    age_periods: int
    created_period: int


class CareServiceQueue:
    """FIFO queue with explicit expiry, survival/retention and capacity.

    A lot created at the end of period t is age 0 at the start of t+1. It gets
    service opportunities during the next max_age_periods periods and expires
    after its final opportunity. Retention models cancellation/obsolescence of
    outstanding claims; it is not a health or welfare discount.
    """

    def __init__(
        self,
        capacity: float,
        max_age_periods: int = 3,
        retention: float = 1.0,
    ):
        if not math.isfinite(capacity) or capacity < 0:
            raise CareQueueError("capacity must be finite and non-negative")
        if not isinstance(max_age_periods, int) or max_age_periods < 1:
            raise CareQueueError("max_age_periods must be a positive integer")
        if not math.isfinite(retention) or not 0.0 <= retention <= 1.0:
            raise CareQueueError("retention must be in [0, 1]")
        self.capacity = float(capacity)
        self.max_age_periods = max_age_periods
        self.retention = float(retention)
        self.lots: list[CareQueueLot] = []
        self.expired_quantity = 0.0
        self.attrited_quantity = 0.0
        self.overflow_quantity = 0.0

    @property
    def total_quantity(self) -> float:
        return sum(lot.quantity for lot in self.lots)

    def serve_fifo(self, quantity: float) -> float:
        if not math.isfinite(quantity) or quantity < 0:
            raise CareQueueError("service quantity must be finite and non-negative")
        remaining = float(quantity)
        served = 0.0
        # Oldest claims first; creation period breaks equal-age ties deterministically.
        ordered = sorted(
            self.lots,
            key=lambda lot: (-lot.age_periods, lot.created_period),
        )
        updated = []
        for lot in ordered:
            take = min(lot.quantity, remaining)
            remaining -= take
            served += take
            left = lot.quantity - take
            if left > EPS:
                updated.append(CareQueueLot(left, lot.age_periods, lot.created_period))
        self.lots = sorted(
            updated, key=lambda lot: (-lot.age_periods, lot.created_period))
        self.validate()
        return served

    def advance_and_add(self, new_unmet: float, period: int) -> dict[str, float]:
        """Age surviving claims, expire old lots, then append current unmet care."""
        if not math.isfinite(new_unmet) or new_unmet < 0:
            raise CareQueueError("new_unmet must be finite and non-negative")
        if not isinstance(period, int) or period < 1:
            raise CareQueueError("period must be a positive integer")

        expired = 0.0
        attrited = 0.0
        aged = []
        for lot in self.lots:
            after_retention = lot.quantity * self.retention
            attrited += lot.quantity - after_retention
            next_age = lot.age_periods + 1
            if next_age >= self.max_age_periods:
                expired += after_retention
            elif after_retention > EPS:
                aged.append(CareQueueLot(
                    after_retention, next_age, lot.created_period))

        self.lots = sorted(
            aged, key=lambda lot: (-lot.age_periods, lot.created_period))
        remaining_capacity = max(0.0, self.capacity - self.total_quantity)
        accepted = min(float(new_unmet), remaining_capacity)
        overflow = float(new_unmet) - accepted
        if accepted > EPS:
            self.lots.append(CareQueueLot(accepted, 0, period))
        self.expired_quantity += expired
        self.attrited_quantity += attrited
        self.overflow_quantity += overflow
        self.validate()
        return {
            "expired": expired,
            "attrited": attrited,
            "accepted_new": accepted,
            "overflow": overflow,
        }

    def age_distribution(self) -> dict[int, float]:
        result = {}
        for lot in self.lots:
            result[lot.age_periods] = result.get(lot.age_periods, 0.0) + lot.quantity
        return result

    def validate(self) -> bool:
        if self.total_quantity > self.capacity + 1e-7:
            raise CareQueueError("care queue exceeds capacity")
        for lot in self.lots:
            if (not math.isfinite(lot.quantity) or lot.quantity < -EPS
                    or lot.age_periods < 0
                    or lot.age_periods >= self.max_age_periods
                    or lot.created_period < 1):
                raise CareQueueError("invalid care queue lot")
        return True
