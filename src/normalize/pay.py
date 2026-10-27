"""Turn extracted pay into comparable numbers: per year and per month.

The model copies pay exactly as the posting states it ("$40/hour", "₹25K/month").
This code does the arithmetic, so it is tested once instead of trusted on every
answer. Currency is never converted: exchange rates change, the posting doesn't.

Assumptions for periods shorter than a month (full-time hours):
    1 year = 52 weeks = 260 working days = 2,080 working hours (40 h x 52)
"""

PER_YEAR = {"hour": 2080, "day": 260, "week": 52, "month": 12, "year": 1}


def yearly_pay(label):
    """{"min", "max", "currency"} per year, or None if the pay can't be computed.

    None when there is no amount, or no period: an amount without a period
    could be per hour or per year, and guessing would be a silent error.
    """
    period = label.get("pay_period")
    if label.get("pay_min") is None or period is None:
        return None
    factor = PER_YEAR[period]
    return {
        "min": round(label["pay_min"] * factor),
        "max": round(label["pay_max"] * factor),
        "currency": label.get("pay_currency"),
    }


def monthly_pay(label):
    """Same as yearly_pay, divided by 12. Internship stipends read better per month."""
    yearly = yearly_pay(label)
    if yearly is None:
        return None
    return {**yearly, "min": round(yearly["min"] / 12), "max": round(yearly["max"] / 12)}
