import re
import os

with open('main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add new imports
imports_to_add = """
import json
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from .database import get_db, engine
from .models import Base
from contextlib import asynccontextmanager
from .rate_limit import check_rate_limit, check_daily_limit, increment_daily_spend, check_idempotency, set_idempotency
"""
code = code.replace("from . import db_reports\n", "from . import db_reports\n" + imports_to_add)

# 2. Add lifespan and cors
lifespan_code = """
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="satsgate", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ORIGINS", "https://agentic.aipp.dev").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""
code = code.replace('app = FastAPI(title="satsgate", version="0.2.0")', lifespan_code)

# 3. Replace db.init_db
code = re.sub(r'try:\s+db\.init_db\(config\.DB_PATH\)\nexcept Exception as e:\s+raise RuntimeError.*', '', code, flags=re.MULTILINE)
code = re.sub(r'# DB init\n\s*', '', code)

# 4. Modify rate limit middleware
rl_mw_new = """
@app.middleware("http")
async def rate_limit_mw(request: Request, call_next):
    if not config.RL_ENABLED:
        return await call_next(request)

    if not request.url.path.startswith("/v1"):
        return await call_next(request)

    x_api_key = request.headers.get("x-api-key")
    key, is_auth = _rate_limit_key(request, x_api_key)

    api_key_hash = key if is_auth else None
    ip = key if not is_auth else "unknown"
    
    allowed, retry_after = await check_rate_limit(api_key_hash, ip)
    if not allowed:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={"ok": False, "error": "rate_limited", "retry_after_seconds": retry_after},
        )

    return await call_next(request)
"""
code = re.sub(r'@app\.middleware\("http"\)\nasync def rate_limit_mw\(request: Request, call_next\):.*?(?=@app\.api_route)', rl_mw_new, code, flags=re.DOTALL)

# 5. Async client fetching
code = code.replace('def _get_client_from_api_key(x_api_key: str | None) -> db.Client | None:', 'async def _get_client_from_api_key(session: AsyncSession, x_api_key: str | None) -> db.Client | None:')
code = code.replace('return db.get_client_by_api_key(config.DB_PATH, x_api_key)', 'return await db.get_client_by_api_key(session, x_api_key)')

# 6. Make all endpoints async and inject session
code = re.sub(r'def v1_(.*?)\(', r'async def v1_\1(session: AsyncSession = Depends(get_db), ', code)
code = re.sub(r'def get_ticket\(', r'async def get_ticket(session: AsyncSession = Depends(get_db), ', code)

code = code.replace('_get_client_from_api_key(x_api_key)', 'await _get_client_from_api_key(session, x_api_key)')

# 7. Update db calls to await and use session
code = code.replace('db_reports.list_ledger(\n        config.DB_PATH,', 'await db_reports.list_ledger(\n        session,')
code = code.replace('db_reports.usage_summary(config.DB_PATH,', 'await db_reports.usage_summary(session,')
code = code.replace('db_reports.usage_daily(config.DB_PATH,', 'await db_reports.usage_daily(session,')
code = code.replace('db_reports.usage_forecast(\n        config.DB_PATH,', 'await db_reports.usage_forecast(\n        session,')

code = code.replace('db_clients.set_client_payee(\n                    config.DB_PATH,', 'await db_clients.set_client_payee(\n                    session,')
code = code.replace('db_clients.set_client_payee(config.DB_PATH,', 'await db_clients.set_client_payee(session,')

code = code.replace('db.spend_credits(\n            config.DB_PATH,', 'await db.spend_credits(\n            session,')

code = code.replace('db.get_topup(config.DB_PATH,', 'await db.get_topup(session,')
code = code.replace('db.create_client(config.DB_PATH)', 'await db.create_client(session)')
code = code.replace('db.settle_topup_and_credit(config.DB_PATH,', 'await db.settle_topup_and_credit(session,')
code = code.replace('db.add_topup(\n            config.DB_PATH,', 'await db.add_topup(\n            session,')

code = code.replace('db_verify.verify_once_and_spend(\n            config.DB_PATH,', 'await db_verify.verify_once_and_spend(\n            session,')

# 8. Add Idempotency and Daily Spend Limit to v1_spend and v1_paywall_verify
idempotency_check = """
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JSONResponse(status_code=400, content={"ok": False, "error": "idempotency_key_required"})
    cached = await check_idempotency(idempotency_key)
    if cached:
        return JSONResponse(content=json.loads(cached))
"""

spend_daily_limit_check = """
    if not await check_daily_limit(db.hash_api_key(x_api_key), int(cost)):
        return JSONResponse(status_code=402, content={"ok": False, "error": "daily_spend_limit_exceeded"})
    await increment_daily_spend(db.hash_api_key(x_api_key), int(cost))
"""

verify_daily_limit_check = """
    if not await check_daily_limit(db.hash_api_key(x_api_key), int(body.cost_credits)):
        return JSONResponse(status_code=402, content={"ok": False, "error": "daily_spend_limit_exceeded"})
    await increment_daily_spend(db.hash_api_key(x_api_key), int(body.cost_credits))
"""

idempotency_save = """
        res_data = {"ok": True, "client_id": client.id, "spent": int(cost), "new_balance": new_balance}
        await set_idempotency(idempotency_key, json.dumps(res_data))
        return res_data
"""

idempotency_save_verify = """
        res_data = {
            "ok": True,
            "client_id": client.id,
            "resource": payload.get("res"),
            "payment_hash": payment_hash,
            "charged_credits": spend["charged"],
            "new_balance": spend["new_balance"],
            "valid_until": payload.get("exp"),
            "note": "Cache by payment_hash until valid_until to avoid calling verify on every request.",
        }
        await set_idempotency(idempotency_key, json.dumps(res_data))
        return res_data
"""

# Apply to v1_spend
v1_spend_sig = 'async def v1_spend(session: AsyncSession = Depends(get_db), \n    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),\n    cost: int = 1,\n):'
v1_spend_sig_new = 'async def v1_spend(request: Request, session: AsyncSession = Depends(get_db), \n    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),\n    cost: int = 1,\n):'
code = code.replace(v1_spend_sig, v1_spend_sig_new)

code = re.sub(r'(async def v1_spend[\s\S]*?if not client:\s+return JSONResponse[^\n]+\n)', r'\1' + idempotency_check + spend_daily_limit_check, code)
code = re.sub(r'return \{"ok": True, "client_id": client.id, "spent": int\(cost\), "new_balance": new_balance\}', idempotency_save.strip(), code)


# Apply to v1_paywall_verify
v1_verify_sig = 'async def v1_paywall_verify(session: AsyncSession = Depends(get_db), \n    body: PaywallVerifyIn,\n    authorization: str | None = Header(default=None),\n    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),\n):'
v1_verify_sig_new = 'async def v1_paywall_verify(request: Request, session: AsyncSession = Depends(get_db), \n    body: PaywallVerifyIn,\n    authorization: str | None = Header(default=None),\n    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),\n):'
code = code.replace(v1_verify_sig, v1_verify_sig_new)

code = re.sub(r'(async def v1_paywall_verify[\s\S]*?if not client:\s+return JSONResponse[^\n]+\n)', r'\1' + idempotency_check + verify_daily_limit_check, code)
code = re.sub(r'return \{\s*"ok": True,\s*"client_id": client.id,\s*"resource": payload\.get\("res"\),\s*"payment_hash": payment_hash,\s*"charged_credits": spend\["charged"\],\s*"new_balance": spend\["new_balance"\],\s*"valid_until": payload\.get\("exp"\),\s*"note": "[^"]+",\s*\}', idempotency_save_verify.strip(), code)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("done")
