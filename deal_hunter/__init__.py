"""deal_hunter — a make-agnostic used/new car deal scanner.

Pulls listings from the Auto.dev API, isolates a target model/variant,
ranks them by price and by discount off MSRP, detects day-over-day price
drops against a stored snapshot, and emails a daily digest.

This instance is configured (via config.yaml) for the Lexus NX 450h+, but
the package itself carries no make-specific logic — point config.yaml at a
different make/model and it works unchanged.
"""

__version__ = "1.0.0"
