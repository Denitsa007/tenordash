import urllib.request
import json
from datetime import date

from config import BASE_CURRENCY

_cache = {"date": None, "rates": None}

# ECB publishes rates vs EUR. We fetch all ECB-available currencies
# and convert to "BASE_CURRENCY per 1 unit of X".
ECB_BASE = "https://data-api.ecb.europa.eu/service/data/EXR/D.{codes}.EUR.SP00.A?lastNObservations=1&format=jsondata"


def _build_ecb_url(currency_codes):
    """Build ECB URL for the given list of currency codes (excluding EUR)."""
    codes = "+".join(sorted(c for c in currency_codes if c != "EUR"))
    if not codes:
        return None
    return ECB_BASE.format(codes=codes)


def clear_cache():
    """Clear daily cache so next call re-fetches from ECB."""
    _cache["date"] = None
    _cache["rates"] = None


def get_fx_rates(currency_rows=None):
    """Fetch latest ECB rates. Returns (rates_dict, date_str).
    rates_dict maps currency -> CHF equivalent of 1 unit of that currency.
    BASE_CURRENCY is always 1.0. EUR and others are converted via EUR cross rates.

    currency_rows: list of sqlite3.Row from currencies table (with code, ecb_available).
    If None, returns cached rates or base-only fallback.
    """
    today = date.today().isoformat()
    if _cache["date"] == today and _cache["rates"] is not None:
        return _cache["rates"], _cache["date"]

    # Determine which codes to fetch
    if currency_rows is not None:
        ecb_codes = [r["code"] for r in currency_rows if r["ecb_available"]]
    else:
        ecb_codes = ["CHF", "GBP", "USD"]  # fallback for standalone calls

    # Always need BASE_CURRENCY in the ECB request (to get the cross-rate anchor)
    fetch_codes = set(ecb_codes)
    if BASE_CURRENCY != "EUR":
        fetch_codes.add(BASE_CURRENCY)
    # EUR is always implicitly the ECB base — no need to include it in the URL
    fetch_codes.discard("EUR")

    url = _build_ecb_url(fetch_codes)
    if url is None:
        # Only EUR in the system
        rates = {BASE_CURRENCY: 1.0, "EUR": 1.0}
        _cache["date"] = today
        _cache["rates"] = rates
        return rates, today

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        dataset = data["dataSets"][0]["series"]
        dims = data["structure"]["dimensions"]["series"]

        # Find which dimension index holds CURRENCY
        ccy_dim_idx = next(i for i, d in enumerate(dims) if d["id"] == "CURRENCY")
        ccy_dim = dims[ccy_dim_idx]
        ccy_map = {i: v["id"] for i, v in enumerate(ccy_dim["values"])}

        raw = {}  # currency -> rate per 1 EUR
        rate_date = None
        for series_key, series_data in dataset.items():
            parts = series_key.split(":")
            ccy_idx = int(parts[ccy_dim_idx])
            ccy = ccy_map[ccy_idx]
            obs = series_data["observations"]
            last_key = max(obs.keys(), key=int)
            raw[ccy] = obs[last_key][0]
            if rate_date is None:
                obs_dates = data["structure"]["dimensions"]["observation"][0]["values"]
                rate_date = obs_dates[int(last_key)]["id"]

        # Convert everything to "BASE_CURRENCY per 1 unit of currency"
        base_per_eur = raw.get(BASE_CURRENCY, 1.0)  # e.g. CHF per 1 EUR
        rates = {BASE_CURRENCY: 1.0, "EUR": base_per_eur}

        for ccy, eur_rate in raw.items():
            if ccy == BASE_CURRENCY:
                continue
            # raw[ccy] = how many units of ccy per 1 EUR
            # BASE_CURRENCY per 1 unit of ccy = base_per_eur / eur_rate
            rates[ccy] = base_per_eur / eur_rate

        _cache["date"] = today
        _cache["rates"] = rates
        return rates, rate_date
    except Exception:
        return _cache.get("rates") or {BASE_CURRENCY: 1.0}, _cache.get("date")


def get_eur_chf_rate():
    """Backwards-compatible: returns (eur_chf_rate, date_str)."""
    rates, rate_date = get_fx_rates()
    return rates.get("EUR"), rate_date


def validate_currency_ecb(code):
    """Check if ECB publishes rates for a given currency code.
    Returns (is_available: bool, error_msg: str|None).
    """
    if code.upper() == "EUR":
        return True, None
    test_url = ECB_BASE.format(codes=code.upper())
    try:
        req = urllib.request.Request(test_url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        # If we get data with observations, it's valid
        dataset = data.get("dataSets", [{}])[0].get("series", {})
        if dataset:
            return True, None
        return False, f"ECB does not publish rates for {code.upper()}"
    except Exception:
        return False, f"Could not verify {code.upper()} against ECB (network error or unsupported currency)"
