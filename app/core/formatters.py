from decimal import Decimal, ROUND_HALF_UP


def money(value) -> float:
    if value is None:
        return 0.00
    return float(
        Decimal(str(value)).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
    )


def money_wan(value) -> float:
    if value is None:
        return 0.00
    yuan = Decimal(str(value))
    wan = yuan / Decimal("10000")
    return float(wan.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))
