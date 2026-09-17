"""
Convert an amount to USD using a free exchange-rate API with static fallbacks.

    usd = await convert_to_usd("1500", "EUR")   # -> "1650"

Returns the amount unchanged if the currency is unknown and no fallback exists.
"""

from collections.abc import Callable
from typing import Any, TypedDict

import aiohttp


class RateAPI(TypedDict):
    name: str
    url: str
    parse_rate: Callable[[dict[str, Any]], float | None]


FALLBACK_RATES = {
    "JPY": 0.0067,
    "EUR": 1.10,
    "GBP": 1.27,
    "CAD": 0.74,
    "AUD": 0.67,
    "CHF": 1.12,
    "CNY": 0.14,
    "KRW": 0.00076,
    "SGD": 0.75,
    "HKD": 0.13,
}


async def convert_to_usd(amount: str, from_currency: str) -> str:
    if from_currency == "USD":
        return amount

    apis: list[RateAPI] = [
        {
            "name": "ExchangeRate-API (free)",
            "url": f"https://api.exchangerate-api.com/v4/latest/{from_currency}",
            "parse_rate": lambda data: data.get("rates", {}).get("USD"),
        }
    ]
    for api in apis:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    api["url"],
                    timeout=aiohttp.ClientTimeout(total=5),
                    headers={"User-Agent": "FastAPI-Application/1.0"},
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        usd_rate = api["parse_rate"](data)
                        if usd_rate and isinstance(usd_rate, (int, float)) and usd_rate > 0:
                            converted_amount = float(amount) * float(usd_rate)
                            return str(int(converted_amount))

        except TimeoutError:
            continue
        except Exception:
            continue
    if from_currency in FALLBACK_RATES:
        fallback_amount = float(amount) * FALLBACK_RATES[from_currency]
        return str(fallback_amount)
    return amount
