from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Client as ClientModel, Ledger, Topup


@dataclass(frozen=True)
class Client:
    id: int
    credits: int
    payee_lightning_address: str | None = None


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def new_api_key() -> str:
    return "sg_" + secrets.token_urlsafe(32)


async def create_client(session: AsyncSession) -> tuple[str, Client]:
    api_key = new_api_key()
    api_key_hash = hash_api_key(api_key)
    now = int(time.time())

    new_client = ClientModel(
        api_key_hash=api_key_hash,
        credits=0,
        created_at=now
    )
    session.add(new_client)
    await session.flush()

    ledger_entry = Ledger(
        client_id=new_client.id,
        delta_credits=0,
        reason="client_created",
        ref=None,
        created_at=now
    )
    session.add(ledger_entry)
    await session.commit()

    return api_key, Client(id=new_client.id, credits=0, payee_lightning_address=None)


async def get_client_by_api_key(session: AsyncSession, api_key: str) -> Client | None:
    if not api_key:
        return None
    h = hash_api_key(api_key)
    
    stmt = select(ClientModel).where(ClientModel.api_key_hash == h)
    result = await session.execute(stmt)
    client_model = result.scalar_one_or_none()
    
    if not client_model:
        return None
    return Client(
        id=client_model.id,
        credits=client_model.credits,
        payee_lightning_address=client_model.payee_lightning_address,
    )


async def add_topup(
    session: AsyncSession,
    *,
    payment_hash: str,
    invoice: str,
    sats: int,
    credits: int,
    client_id: int | None,
) -> None:
    now = int(time.time())
    new_topup = Topup(
        payment_hash=payment_hash,
        invoice=invoice,
        sats=sats,
        credits=credits,
        status='pending',
        client_id=client_id,
        created_at=now
    )
    session.add(new_topup)
    await session.commit()


async def get_topup(session: AsyncSession, payment_hash: str) -> dict | None:
    stmt = select(Topup).where(Topup.payment_hash == payment_hash)
    result = await session.execute(stmt)
    topup = result.scalar_one_or_none()
    if not topup:
        return None
    return {
        "id": topup.id,
        "payment_hash": topup.payment_hash,
        "invoice": topup.invoice,
        "sats": topup.sats,
        "credits": topup.credits,
        "status": topup.status,
        "client_id": topup.client_id,
        "created_at": topup.created_at,
        "settled_at": topup.settled_at,
    }


async def settle_topup_and_credit(
    session: AsyncSession,
    *,
    payment_hash: str,
    client_id: int,
) -> dict:
    now = int(time.time())

    stmt = select(Topup).where(Topup.payment_hash == payment_hash).with_for_update()
    result = await session.execute(stmt)
    topup = result.scalar_one_or_none()

    if not topup:
        raise ValueError("topup not found")

    if topup.status == "settled":
        bal_stmt = select(ClientModel.credits).where(ClientModel.id == client_id)
        bal_res = await session.execute(bal_stmt)
        bal = bal_res.scalar()
        return {"credits_added": 0, "new_balance": bal if bal else 0}

    credits_added = topup.credits

    if topup.client_id is not None and topup.client_id != client_id:
        raise ValueError("this topup belongs to a different client")

    topup.status = 'settled'
    topup.client_id = client_id
    topup.settled_at = now

    client_stmt = select(ClientModel).where(ClientModel.id == client_id).with_for_update()
    client_res = await session.execute(client_stmt)
    client = client_res.scalar_one()
    client.credits += credits_added

    ledger_entry = Ledger(
        client_id=client_id,
        delta_credits=credits_added,
        reason="topup_settled",
        ref=payment_hash,
        created_at=now
    )
    session.add(ledger_entry)

    await session.commit()

    return {"credits_added": credits_added, "new_balance": client.credits}


async def spend_credits(session: AsyncSession, *, client_id: int, cost: int, reason: str, ref: str | None = None) -> int:
    now = int(time.time())
    cost = int(cost)
    
    if cost <= 0:
        return await get_balance(session, client_id=client_id)

    client_stmt = select(ClientModel).where(ClientModel.id == client_id).with_for_update()
    result = await session.execute(client_stmt)
    client = result.scalar_one_or_none()

    if not client:
        raise ValueError("client does not exist")

    if client.credits < cost:
        raise ValueError("insufficient balance")

    client.credits -= cost

    ledger_entry = Ledger(
        client_id=client_id,
        delta_credits=-cost,
        reason=reason,
        ref=ref,
        created_at=now
    )
    session.add(ledger_entry)

    await session.commit()
    return client.credits


async def get_balance(session: AsyncSession, *, client_id: int) -> int:
    stmt = select(ClientModel.credits).where(ClientModel.id == client_id)
    result = await session.execute(stmt)
    credits = result.scalar_one_or_none()
    return credits if credits is not None else 0
