import pytest

from src.normalize.pay import monthly_pay, yearly_pay


def pay(low, high, currency, period):
    return {"pay_min": low, "pay_max": high, "pay_currency": currency, "pay_period": period}


@pytest.mark.parametrize("label, expected", [
    (pay(40, 40, "USD", "hour"), {"min": 83200, "max": 83200, "currency": "USD"}),         # $40/hour
    (pay(25000, 25000, "INR", "month"), {"min": 300000, "max": 300000, "currency": "INR"}),  # ₹25K/month
    (pay(600000, 700000, "INR", "year"), {"min": 600000, "max": 700000, "currency": "INR"}),  # 6-7 LPA
    (pay(1500, 2000, "EUR", "week"), {"min": 78000, "max": 104000, "currency": "EUR"}),
    (pay(3000, 3000, "INR", "day"), {"min": 780000, "max": 780000, "currency": "INR"}),
])
def test_yearly_pay(label, expected):
    assert yearly_pay(label) == expected


def test_monthly_pay_of_a_yearly_salary():
    assert monthly_pay(pay(600000, 720000, "INR", "year")) == {"min": 50000, "max": 60000, "currency": "INR"}


def test_monthly_pay_keeps_a_monthly_stipend_unchanged():
    assert monthly_pay(pay(25000, 25000, "INR", "month"))["min"] == 25000


@pytest.mark.parametrize("label", [
    pay(None, None, None, None),          # no pay stated
    pay(None, None, None, "month"),       # "Competitive monthly stipend": period but no amount
    pay(150000, 150000, "USD", None),     # amount without a period: per hour? per year? don't guess
])
def test_no_number_when_pay_cant_be_computed(label):
    assert yearly_pay(label) is None
    assert monthly_pay(label) is None


def test_currency_is_never_converted():
    assert yearly_pay(pay(100, 100, "GBP", "day"))["currency"] == "GBP"
