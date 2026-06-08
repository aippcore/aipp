from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Client as ClientModel, Ledger, Verification


async def verify_once_and_spend(
    session: AsyncSession,
    *,
    client_id: int,
    payment_hash: str,
    cost: int,
    resource: str | None = None,
) -> dict:
    now = int(time.time())
    cost = int(cost)

    stmt_ver = select(Verification).where(
        Verification.client_id == client_id,
        Verification.payment_hash == payment_hash
    ).with_for_update()
    
    result_ver = await session.execute(stmt_ver)
    verification = result_ver.scalar_one_or_none()

    if verification:
        bal_stmt = select(ClientModel.credits).where(ClientModel.id == client_id)
        bal_res = await session.execute(bal_stmt)
        bal = bal_res.scalar()
        return {"charged": 0, "new_balance": bal if bal else 0}

    client_stmt = select(ClientModel).where(ClientModel.id == client_id).with_for_update()
    client_res = await session.execute(client_stmt)
    client = client_res.scalar_one_or_none()

    if not client:
        raise ValueError("client does not exist")

    if client.credits < cost:
        raise ValueError("insufficient balance")

    client.credits -= cost

    ledger_entry = Ledger(
        client_id=client_id,
        delta_credits=-cost,
        reason="paywall_verify",
        ref=payment_hash,
        created_at=now
    )
    session.add(ledger_entry)

    new_verification = Verification(
        client_id=client_id,
        payment_hash=payment_hash,
        resource=resource,
        created_at=now
    )
    session.add(new_verification)

    await session.commit()

    return {"charged": cost, "new_balance": client.credits}
