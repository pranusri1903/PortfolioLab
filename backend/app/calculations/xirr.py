from datetime import date

MIN_DAYS = 30  # shorter horizons annualise into meaningless numbers


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Annualised money-weighted return. Negative = money paid in, positive = money received.
    Returns None if undefined (no sign change, too short, or no root in [-99%, +10000%])."""
    if not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    t0 = min(d for d, _ in flows)
    if (max(d for d, _ in flows) - t0).days < MIN_DAYS:
        return None

    def npv(r: float) -> float:
        return sum(v / (1 + r) ** ((d - t0).days / 365) for d, v in flows)

    lo, hi = -0.99, 100.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):  # bisection: slow but cannot diverge
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(lo) * npv(mid) > 0 else (lo, mid)
    return (lo + hi) / 2
