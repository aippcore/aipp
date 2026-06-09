import os
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine

# Set environment variables for tests before any modules are imported
os.environ["SATSGATE_WALLET_MODE"] = "mock"
os.environ["SATSGATE_DEV_MODE"] = "1"
os.environ["SATSGATE_RL_ENABLED"] = "0"
os.environ["SATSGATE_MACAROON_SECRET"] = "test-secret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///satsgate_test.sqlite3"
os.environ["SATSGATE_ADMIN_TOKEN"] = "test-admin-token"

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    from app.models import Base
    
    async def init_db():
        engine = create_async_engine(os.environ["DATABASE_URL"])
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        
    asyncio.run(init_db())
