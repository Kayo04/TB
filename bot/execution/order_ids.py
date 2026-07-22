"""
Deterministic client_order_id generation -- the sole implementation shared by
every Broker (PaperBroker today, a future LiveBroker later), so the ID scheme
itself is never reimplemented per broker (the same drift risk milestone 1's
parity test guards against for Strategy).

Inputs are chosen to be exactly what's stable across a crash/restart replay:
- strategy_name, not anything about *how* the strategy computed the signal --
  cheap collision guard between two strategies deciding on the same symbol/bar.
- effective_ts, canonicalized to UTC before hashing -- NOT wall-clock submission
  time, which changes on every retry.
- from_position/to_position -- redundant while positions are 0/1, but doesn't
  hard-code "only two transition types," so shorts/fractional sizing later
  don't force an ID-scheme rewrite.

This determinism depends on Strategy.compute_signal being pure (milestone 1's
contract) -- if replaying the same bars could yield a different signal, the
same input->same ID chain breaks upstream of this function entirely.
"""

from __future__ import annotations
import hashlib
import pandas as pd

_MAX_TAG_LEN = 8


def make_client_order_id(
    strategy_name: str,
    symbol: str,
    effective_ts: pd.Timestamp,
    from_position: int,
    to_position: int,
) -> str:
    ts = pd.Timestamp(effective_ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    canonical_ts = ts.isoformat()

    symbol_safe = symbol.replace("/", "-")
    composite = f"{strategy_name}|{symbol_safe}|{canonical_ts}|{from_position}->{to_position}"
    digest = hashlib.sha256(composite.encode("utf-8")).hexdigest()[:24]

    tag = "".join(ch for ch in strategy_name if ch.isalnum())[:_MAX_TAG_LEN] or "strat"
    return f"{tag}_{digest}"
