from datetime import date, timedelta
from config import CONTINUATION_DAYS, INTEREST_YEAR_BASIS


def calc_days(start_date_str, end_date_str):
    """Calculate number of days between two ISO date strings."""
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    return (end - start).days


def calc_interest_rate_pa(interest_amount, amount_original, days):
    """Back-calculate annual interest rate using 360-day convention."""
    if days <= 0 or amount_original <= 0:
        return 0.0
    return (interest_amount / amount_original) * (INTEREST_YEAR_BASIS / days) * 100


def suggest_continuation_date(end_date_str):
    """Suggest continuation date: 3 business days before end date (skip weekends)."""
    end = date.fromisoformat(end_date_str)
    bdays = 0
    current = end
    while bdays < CONTINUATION_DAYS:
        current -= timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            bdays += 1
    return current.isoformat()


def is_currently_active(start_date_str, end_date_str):
    """Check if advance is currently active."""
    today = date.today()
    start = date.fromisoformat(start_date_str)
    end = date.fromisoformat(end_date_str)
    return start <= today < end


def format_amount_short(amount):
    """Format amount for display: 80000000 -> '80M'."""
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        m = amount / 1_000_000
        return f"{m:,.0f}M" if m == int(m) else f"{m:,.1f}M"
    return f"{amount:,.0f}"


def format_amount(amount):
    """Format amount with thousand separators."""
    return f"{amount:,.0f}"


def enrich_advance(row):
    """Add calculated fields to an advance dict."""
    d = dict(row)
    d["days"] = calc_days(d["start_date"], d["end_date"])
    d["rate_pa"] = calc_interest_rate_pa(
        d["interest_amount"], d["amount_original"], d["days"]
    )
    d["active"] = is_currently_active(d["start_date"], d["end_date"])
    return d
