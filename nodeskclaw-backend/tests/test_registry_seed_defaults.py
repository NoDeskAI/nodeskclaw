from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
from app.models.system_config import SystemConfig
from app.startup.seed import DEFAULT_REGISTRY_CONFIGS, _seed_default_registry_configs

TEST_DATABASE_URL = "postgresql+asyncpg://nodeskclaw:nodeskclaw@localhost:5432/nodeskclaw_test"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        yield False
        return

    yield True

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_seed_default_registry_configs_upgrades_legacy_hermes_registry(setup_db):
    if not setup_db:
        pytest.skip("test database unavailable")

    suffix = uuid4().hex[:8]
    legacy_key = f"legacy-marker-{suffix}"

    async with TestSessionLocal() as db:
        db.add(SystemConfig(key="image_registry_hermes", value="nousresearch/hermes-agent"))
        db.add(SystemConfig(key=legacy_key, value="keep"))
        await db.commit()

    await _seed_default_registry_configs(TestSessionLocal)

    async with TestSessionLocal() as db:
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == "image_registry_hermes")
        )
        row = result.scalar_one()

        untouched = await db.execute(
            select(SystemConfig).where(SystemConfig.key == legacy_key)
        )
        untouched_row = untouched.scalar_one()

        assert (
            row.value
            == DEFAULT_REGISTRY_CONFIGS["image_registry_hermes"]
            == "ghcr.io/routin/deskclaw-hermes"
        )
        assert untouched_row.value == "keep"
