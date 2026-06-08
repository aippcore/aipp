from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def _iso(ts: int) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()


async def list_ledger(
    session: AsyncSession,
    *,
    client_id: int,
    limit: int = 50,
    before_id: int | None = None,
) -> list[dict]:
    limit = max(1, min(int(limit), 200))

    sql = """
        SELECT id, delta_credits, reason, ref, created_at
        FROM ledger WHERE client_id = :client_id
    """
    params = {"client_id": int(client_id), "limit": limit}

    if before_id is not None:
        sql += " AND id < :before_id"
        params["before_id"] = int(before_id)

    sql += " ORDER BY id DESC LIMIT :limit"

    result = await session.execute(text(sql), params)
    rows = result.fetchall()

    out: list[dict] = []
    for r in rows:
        ts = int(r.created_at)
        out.append(
            {
                "id": int(r.id),
                "delta_credits": int(r.delta_credits),
                "reason": r.reason,
                "ref": r.ref,
                "created_at": ts,
                "created_at_iso": _iso(ts),
            }
        )
    return out


async def usage_summary(
    session: AsyncSession,
    *,
    client_id: int,
    since_ts: int,
) -> dict:
    since_ts = int(since_ts)

    row_result = await session.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN delta_credits > 0 THEN delta_credits ELSE 0 END), 0) AS credits_in,
            COALESCE(SUM(CASE WHEN delta_credits < 0 THEN -delta_credits ELSE 0 END), 0) AS credits_out,
            COALESCE(SUM(delta_credits), 0) AS net_credits,
            COALESCE(SUM(CASE WHEN reason = 'paywall_verify' THEN 1 ELSE 0 END), 0) AS verify_events,
            COALESCE(SUM(CASE WHEN reason = 'topup_settled' THEN 1 ELSE 0 END), 0) AS topup_events
        FROM ledger
        WHERE client_id = :client_id AND created_at >= :since_ts
    """), {"client_id": int(client_id), "since_ts": since_ts})
    row = row_result.fetchone()

    rows_result = await session.execute(text("""
        SELECT
            reason,
            COUNT(*) AS events,
            COALESCE(SUM(delta_credits), 0) AS net_credits,
            COALESCE(SUM(CASE WHEN delta_credits > 0 THEN delta_credits ELSE 0 END), 0) AS credits_in,
            COALESCE(SUM(CASE WHEN delta_credits < 0 THEN -delta_credits ELSE 0 END), 0) AS credits_out
        FROM ledger
        WHERE client_id = :client_id AND created_at >= :since_ts
        GROUP BY reason
        ORDER BY events DESC
    """), {"client_id": int(client_id), "since_ts": since_ts})
    rows = rows_result.fetchall()

    by_reason = []
    for r in rows:
        by_reason.append(
            {
                "reason": r.reason,
                "events": int(r.events),
                "net_credits": int(r.net_credits),
                "credits_in": int(r.credits_in),
                "credits_out": int(r.credits_out),
            }
        )

    return {
        "since_ts": since_ts,
        "since_iso": _iso(since_ts),
        "credits_in": int(row.credits_in),
        "credits_out": int(row.credits_out),
        "net_credits": int(row.net_credits),
        "verify_events": int(row.verify_events),
        "topup_events": int(row.topup_events),
        "by_reason": by_reason,
    }


async def usage_daily(
    session: AsyncSession,
    *,
    client_id: int,
    days: int,
    now_ts: int | None = None,
) -> dict:
    days = max(1, min(int(days), 366))

    if now_ts is None:
        now_dt = datetime.now(timezone.utc)
    else:
        now_dt = datetime.fromtimestamp(int(now_ts), tz=timezone.utc)

    today = now_dt.date()
    start_day = today - timedelta(days=days - 1)

    def midnight_ts(day) -> int:
        return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())

    start_ts = midnight_ts(start_day)
    end_ts = midnight_ts(today + timedelta(days=1))

    # NOTE: date(created_at, 'unixepoch') is SQLite specific. For Postgres we need something else.
    # We will use Postgres to_timestamp(created_at)::date
    # Since we are using PostgreSQL asyncpg, we will adjust this query for postgres.
    result = await session.execute(text("""
        SELECT
            to_timestamp(created_at)::date AS day,
            COALESCE(SUM(CASE WHEN delta_credits > 0 THEN delta_credits ELSE 0 END), 0) AS credits_in,
            COALESCE(SUM(CASE WHEN delta_credits < 0 THEN -delta_credits ELSE 0 END), 0) AS credits_out,
            COALESCE(SUM(delta_credits), 0) AS net_credits,
            COALESCE(SUM(CASE WHEN reason = 'paywall_verify' THEN 1 ELSE 0 END), 0) AS verify_events,
            COALESCE(SUM(CASE WHEN reason = 'topup_settled' THEN 1 ELSE 0 END), 0) AS topup_events
        FROM ledger
        WHERE client_id = :client_id AND created_at >= :start_ts AND created_at < :end_ts
        GROUP BY day
        ORDER BY day ASC
    """), {"client_id": int(client_id), "start_ts": start_ts, "end_ts": end_ts})
    rows = result.fetchall()

    by_day: dict[str, dict] = {}
    for r in rows:
        by_day[str(r.day)] = {
            "credits_in": int(r.credits_in),
            "credits_out": int(r.credits_out),
            "net_credits": int(r.net_credits),
            "verify_events": int(r.verify_events),
            "topup_events": int(r.topup_events),
        }

    series: list[dict] = []
    for i in range(days):
        day = start_day + timedelta(days=i)
        day_str = day.isoformat()
        day_start = midnight_ts(day)
        day_end = midnight_ts(day + timedelta(days=1))

        m = by_day.get(
            day_str,
            {
                "credits_in": 0,
                "credits_out": 0,
                "net_credits": 0,
                "verify_events": 0,
                "topup_events": 0,
            },
        )

        series.append(
            {
                "day": day_str,
                "day_start_ts": day_start,
                "day_start_iso": _iso(day_start),
                "day_end_ts": day_end,
                "credits_in": int(m["credits_in"]),
                "credits_out": int(m["credits_out"]),
                "net_credits": int(m["net_credits"]),
                "verify_events": int(m["verify_events"]),
                "topup_events": int(m["topup_events"]),
            }
        )

    return {
        "tz": "UTC",
        "days": days,
        "start_ts": start_ts,
        "start_iso": _iso(start_ts),
        "end_ts": end_ts,
        "end_iso": _iso(end_ts),
        "series": series,
    }


async def usage_forecast(
    session: AsyncSession,
    *,
    client_id: int,
    current_balance_credits: int,
    lookback_hours: int = 24,
    now_ts: int | None = None,
) -> dict:
    lookback_hours = max(1, min(int(lookback_hours), 24 * 30))
    current_balance_credits = max(0, int(current_balance_credits))

    if now_ts is None:
        now_dt = datetime.now(timezone.utc)
        now_ts = int(now_dt.timestamp())
    else:
        now_ts = int(now_ts)

    window_seconds = lookback_hours * 3600
    since_ts = now_ts - window_seconds

    result = await session.execute(text("""
        SELECT
            COALESCE(SUM(CASE WHEN reason = 'paywall_verify' AND delta_credits < 0 THEN -delta_credits ELSE 0 END), 0) AS verify_credits_out,
            COALESCE(SUM(CASE WHEN delta_credits < 0 THEN -delta_credits ELSE 0 END), 0) AS total_credits_out,
            COALESCE(SUM(CASE WHEN reason = 'paywall_verify' THEN 1 ELSE 0 END), 0) AS verify_events,
            COALESCE(SUM(CASE WHEN delta_credits < 0 THEN 1 ELSE 0 END), 0) AS spend_events,
            MAX(CASE WHEN reason = 'paywall_verify' THEN created_at ELSE NULL END) AS last_verify_at
        FROM ledger
        WHERE client_id = :client_id AND created_at >= :since_ts
    """), {"client_id": int(client_id), "since_ts": since_ts})
    row = result.fetchone()

    verify_credits_out = int(row.verify_credits_out)
    total_credits_out = int(row.total_credits_out)
    verify_events = int(row.verify_events)
    spend_events = int(row.spend_events)

    last_verify_at = row.last_verify_at
    last_verify_ts = int(last_verify_at) if last_verify_at is not None else None

    verify_rate_credits_per_hour = verify_credits_out / float(lookback_hours)
    verify_rate_verifies_per_hour = verify_events / float(lookback_hours)

    avg_credits_per_verify: float | None = None
    if verify_events > 0:
        avg_credits_per_verify = verify_credits_out / float(verify_events)

    estimated_hours_remaining: float | None = None
    estimated_depletion_ts: int | None = None

    if verify_rate_credits_per_hour > 0:
        estimated_hours_remaining = current_balance_credits / verify_rate_credits_per_hour
        estimated_depletion_ts = int(now_ts + (estimated_hours_remaining * 3600))

    if verify_events == 0:
        status = "insufficient_data"
    elif verify_events < 10:
        status = "low_sample"
    else:
        status = "ok"

    verify_rate_credits_per_day = verify_rate_credits_per_hour * 24.0
    verify_rate_verifies_per_day = verify_rate_verifies_per_hour * 24.0

    estimated_days_remaining: float | None = None
    if estimated_hours_remaining is not None:
        estimated_days_remaining = estimated_hours_remaining / 24.0

    return {
        "status": status,
        "tz": "UTC",
        "now_ts": now_ts,
        "now_iso": _iso(now_ts),
        "since_ts": since_ts,
        "since_iso": _iso(since_ts),
        "lookback_hours": lookback_hours,
        "current_balance_credits": current_balance_credits,
        "verify_events": verify_events,
        "verify_credits_out": verify_credits_out,
        "total_credits_out": total_credits_out,
        "spend_events": spend_events,
        "avg_credits_per_verify": avg_credits_per_verify,
        "verify_rate_credits_per_hour": verify_rate_credits_per_hour,
        "verify_rate_credits_per_day": verify_rate_credits_per_day,
        "verify_rate_verifies_per_hour": verify_rate_verifies_per_hour,
        "verify_rate_verifies_per_day": verify_rate_verifies_per_day,
        "estimated_hours_remaining": estimated_hours_remaining,
        "estimated_days_remaining": estimated_days_remaining,
        "estimated_depletion_ts": estimated_depletion_ts,
        "estimated_depletion_iso": _iso(estimated_depletion_ts) if estimated_depletion_ts else None,
        "last_verify_ts": last_verify_ts,
        "last_verify_iso": _iso(last_verify_ts) if last_verify_ts else None,
        "note": "Simple forecast based on the lookback window. If your traffic is irregular, treat it as guidance.",
    }
