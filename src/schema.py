"""The extraction schema: the JSON every model must output for one posting.

These rules double as the labelling guidelines:
- Every key is always present. Not stated in the posting -> null for single
  values, [] for lists. Never guess, never use outside knowledge.
- Pay is copied in the currency and period the posting states, with shorthand
  expanded: "$150K" -> 150000, "6 LPA" -> 600000 per year, "₹15K/month" -> 15000.
  A single amount sets pay_min = pay_max. Converting between currencies or
  periods is done later by tested code, never by the model.
- Duration is copied as stated: "12-week internship" -> 12, "week".
"""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION = 1

YearMonth = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]  # "2027-06"
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]  # ISO 4217: USD, INR, EUR
Amount = Annotated[float, Field(ge=0)]
BatchYear = Annotated[int, Field(ge=2000, le=2040)]


class JobPosting(BaseModel):
    model_config = ConfigDict(
        extra="forbid",  # an invented key is an error, not silently dropped
        str_strip_whitespace=True,
        str_min_length=1,  # "" is not a value; use null instead
    )

    # Who and what
    company: str | None
    role: str | None
    job_type: Literal["internship", "full_time", "part_time", "contract"] | None
    work_mode: Literal["onsite", "remote", "hybrid"] | None
    locations: list[str]
    skills: list[str]

    # When
    start: YearMonth | None
    deadline: date | None  # "2026-11-30"; impossible dates like 2026-02-30 fail
    duration_value: Annotated[float, Field(gt=0)] | None
    duration_unit: Literal["week", "month"] | None

    # Pay, exactly as stated
    pay_min: Amount | None
    pay_max: Amount | None
    pay_currency: CurrencyCode | None
    pay_period: Literal["hour", "day", "week", "month", "year"] | None
    pay_raw: str | None  # the original pay text, e.g. "$150,000 - $200,000 USD"

    # Eligibility (rare in our data; reported separately)
    eligible_batches: list[BatchYear]
    min_gpa: Annotated[float, Field(ge=0, le=10)] | None
    fee_required: bool | None

    @model_validator(mode="after")
    def check_consistency(self):
        if self.pay_min is not None and self.pay_max is not None and self.pay_min > self.pay_max:
            raise ValueError("pay_min is greater than pay_max")
        if (self.pay_min is not None or self.pay_max is not None) and self.pay_raw is None:
            raise ValueError("pay numbers need pay_raw, the text they came from")
        if (self.duration_value is None) != (self.duration_unit is None):
            raise ValueError("duration_value and duration_unit must be set together")
        return self
