from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Client as ClientModel, Ledger


async def set_client_payee(session: AsyncSession, *, client_id: int, payee_lightning_address: str | None) -> None:
    now = int(time.time())
    
    stmt = select(ClientModel).where(ClientModel.id == client_id).with_for_update()
    result = await session.execute(stmt)
    client = result.scalar_one_or_none()

    if not client:
        raise ValueError("client does not exist")

    client.payee_lightning_address = payee_lightning_address

    ledger_entry = Ledger(
        client_id=client_id,
        delta_credits=0,
        reason="payee_set",
        ref=payee_lightning_address,
        created_at=now
    )
    session.add(ledger_entry)

    await session.commit()


async def get_client_payee(session: AsyncSession, *, client_id: int) -> str | None:
    stmt = select(ClientModel.payee_lightning_address).where(ClientModel.id == client_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
