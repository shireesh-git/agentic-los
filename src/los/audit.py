"""R18 — audit integrity: a per-application sequence and hash chain.

Each event carries `seq` (its 1-based position in the application's log) and
`prev_hash` (the hash of the previous event). `event_hash` folds the identity,
the sequence, the previous hash and the payload into a digest; `verify_audit`
recomputes the chain and reports whether it is intact and where it breaks.
"""
from __future__ import annotations

import hashlib
import json

HASH_LEN = 64


def _norm(value) -> str:
    if value is None:
        return ""
    return str(value)


def event_hash(event: dict, prev_hash: str = "") -> str:
    """The digest that binds one event to the one before it."""
    payload = {
        "seq": event.get("seq"),
        "prev_hash": prev_hash or "",
        "at": _norm(event.get("at")),
        "actor_id": _norm(event.get("actor_id")),
        "actor_role": _norm(event.get("actor_role")),
        "action": _norm(event.get("action")),
        "from_step": _norm(event.get("from_step")),
        "to_step": _norm(event.get("to_step")),
        "status": _norm(event.get("status")),
        "comment": _norm(event.get("comment")),
        "detail": json.dumps(event.get("detail") or {}, sort_keys=True, default=str),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def chain_hash(events: list[dict]) -> tuple[str, list[dict]]:
    """Walk the (oldest-first) events, computing each hash from the previous one.

    Returns (final_hash, computed) where computed is the list of
    {seq, hash} for verification against the stored values."""
    prev = ""
    computed: list[dict] = []
    for i, e in enumerate(events, start=1):
        h = event_hash(e, prev)
        computed.append({"seq": i, "hash": h})
        prev = h
    return prev, computed


def verify_audit(events: list[dict]) -> dict:
    """Verify a (oldest-first) event list: the sequence must be 1..n and each event's
    recorded hash (if any) must match the recomputed chain. Events without stored
    hashes are verified against the chain alone (they were recorded before the
    chain existed, or the store is being seeded)."""
    events = list(events)
    _, computed = chain_hash(events)
    valid = True
    broken_at = None
    for i, e in enumerate(events, start=1):
        if e.get("seq") not in (None, i):
            valid = False
            broken_at = i
            break
        stored = e.get("hash")
        if stored and stored != computed[i - 1]["hash"]:
            valid = False
            broken_at = i
            break
    return {"valid": valid, "broken_at_seq": broken_at, "count": len(events),
            "final_hash": computed[-1]["hash"] if computed else ""}
