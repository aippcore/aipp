from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def _iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()

async def operator_overview(session: AsyncSession, *, since_ts: int) -> dict:
    since_ts = int(since_ts)

    # Note: Since the queries are independent and mostly aggregations, 
    # we can do them one by one or in bigger queries.

    clients_total = await session.execute(text("SELECT COUNT(*) FROM clients"))
    clients_total_val = clients_total.scalar()

    credits_outstanding = await session.execute(text("SELECT COALESCE(SUM(credits),0) FROM clients"))
    credits_outstanding_val = credits_outstanding.scalar()

    clients_new = await session.execute(text("SELECT COUNT(*) FROM clients WHERE created_at >= :since_ts"), {"since_ts": since_ts})
    clients_new_val = clients_new.scalar()

    topups_pending = await session.execute(text("SELECT COUNT(*) FROM topups WHERE status='pending'"))
    topups_pending_val = topups_pending.scalar()

    topups_settled_count = await session.execute(
        text("SELECT COUNT(*) FROM topups WHERE status='settled' AND settled_at >= :since_ts"), 
        {"since_ts": since_ts}
    )
    topups_settled_count_val = topups_settled_count.scalar()

    topups_sats_sum = await session.execute(
        text("SELECT COALESCE(SUM(sats),0) FROM topups WHERE status='settled' AND settled_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    topups_sats_sum_val = topups_sats_sum.scalar()

    topups_credits_sum = await session.execute(
        text("SELECT COALESCE(SUM(credits),0) FROM topups WHERE status='settled' AND settled_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    topups_credits_sum_val = topups_credits_sum.scalar()

    verify_events = await session.execute(
        text("SELECT COALESCE(SUM(CASE WHEN reason='paywall_verify' THEN 1 ELSE 0 END),0) FROM ledger WHERE created_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    verify_events_val = verify_events.scalar()

    verify_credits_spent = await session.execute(
        text("SELECT COALESCE(SUM(CASE WHEN reason='paywall_verify' AND delta_credits < 0 THEN -delta_credits ELSE 0 END),0) FROM ledger WHERE created_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    verify_credits_spent_val = verify_credits_spent.scalar()

    credits_in = await session.execute(
        text("SELECT COALESCE(SUM(CASE WHEN delta_credits > 0 THEN delta_credits ELSE 0 END),0) FROM ledger WHERE created_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    credits_in_val = credits_in.scalar()

    credits_out = await session.execute(
        text("SELECT COALESCE(SUM(CASE WHEN delta_credits < 0 THEN -delta_credits ELSE 0 END),0) FROM ledger WHERE created_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    credits_out_val = credits_out.scalar()

    net_credits = await session.execute(
        text("SELECT COALESCE(SUM(delta_credits),0) FROM ledger WHERE created_at >= :since_ts"),
        {"since_ts": since_ts}
    )
    net_credits_val = net_credits.scalar()

    last_topup_settled = await session.execute(
        text("SELECT MAX(settled_at) FROM topups WHERE status='settled'")
    )
    last_topup_settled_val = last_topup_settled.scalar()

    last_verify = await session.execute(
        text("SELECT MAX(created_at) FROM ledger WHERE reason='paywall_verify'")
    )
    last_verify_val = last_verify.scalar()

    # Recent topups
    recent_topups_query = await session.execute(
        text("SELECT id, client_id, sats, credits, status, created_at, settled_at FROM topups ORDER BY created_at DESC LIMIT 10")
    )
    recent_topups = [dict(row._mapping) for row in recent_topups_query]
    for r in recent_topups:
        r["created_iso"] = _iso(r["created_at"])
        r["settled_iso"] = _iso(r["settled_at"])

    # Recent verifications
    recent_verifications_query = await session.execute(
        text("SELECT id, client_id, delta_credits, created_at FROM ledger WHERE reason='paywall_verify' ORDER BY created_at DESC LIMIT 10")
    )
    recent_verifications = [dict(row._mapping) for row in recent_verifications_query]
    for r in recent_verifications:
        r["created_iso"] = _iso(r["created_at"])

    # Daily metrics (last 7 days)
    seven_days_ago = int(datetime.now(timezone.utc).timestamp()) - (7 * 24 * 3600)
    
    daily_topups_query = await session.execute(
        text("""
            SELECT settled_at, sats
            FROM topups 
            WHERE status='settled' AND settled_at >= :ts
        """), {"ts": seven_days_ago}
    )
    daily_topups_dict = {}
    for row in daily_topups_query:
        day = datetime.fromtimestamp(row.settled_at, tz=timezone.utc).strftime('%Y-%m-%d')
        daily_topups_dict[day] = daily_topups_dict.get(day, 0) + row.sats
    daily_topups = [{"day": k, "sats_sum": v} for k, v in sorted(daily_topups_dict.items())]

    daily_verifications_query = await session.execute(
        text("""
            SELECT created_at
            FROM ledger 
            WHERE reason='paywall_verify' AND created_at >= :ts
        """), {"ts": seven_days_ago}
    )
    daily_verifications_dict = {}
    for row in daily_verifications_query:
        day = datetime.fromtimestamp(row.created_at, tz=timezone.utc).strftime('%Y-%m-%d')
        daily_verifications_dict[day] = daily_verifications_dict.get(day, 0) + 1
    daily_verifications = [{"day": k, "count": v} for k, v in sorted(daily_verifications_dict.items())]

    return {
        "since_ts": since_ts,
        "since_iso": _iso(since_ts),
        "totals": {
            "clients_total": int(clients_total_val),
            "credits_outstanding": int(credits_outstanding_val),
            "topups_pending": int(topups_pending_val),
        },
        "window": {
            "clients_new": int(clients_new_val),
            "topups_settled_count": int(topups_settled_count_val),
            "topups_sats_sum": int(topups_sats_sum_val),
            "topups_credits_sum": int(topups_credits_sum_val),
            "verify_events": int(verify_events_val),
            "verify_credits_spent": int(verify_credits_spent_val),
            "credits_in": int(credits_in_val),
            "credits_out": int(credits_out_val),
            "net_credits": int(net_credits_val),
        },
        "last_seen": {
            "topup_settled_ts": int(last_topup_settled_val) if last_topup_settled_val is not None else None,
            "topup_settled_iso": _iso(last_topup_settled_val),
            "verify_ts": int(last_verify_val) if last_verify_val is not None else None,
            "verify_iso": _iso(last_verify_val),
        },
        "recent_topups": recent_topups,
        "recent_verifications": recent_verifications,
        "daily_topups": daily_topups,
        "daily_verifications": daily_verifications,
        "note": "Operator overview. Values are derived from the database and are best-effort.",
    }
