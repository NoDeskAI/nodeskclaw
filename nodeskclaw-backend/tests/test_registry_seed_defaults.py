import pytest

from app.models.system_config import SystemConfig
from app.startup.seed import DEFAULT_REGISTRY_CONFIGS, _seed_default_registry_configs


class FakeExecuteResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.keys = iter(DEFAULT_REGISTRY_CONFIGS)
        self.commit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info):
        return None

    async def execute(self, _statement):
        key = next(self.keys)
        return FakeExecuteResult(self.rows.get(key))

    def add(self, row):
        self.rows[row.key] = row

    async def commit(self):
        self.commit_count += 1


@pytest.mark.parametrize(
    "legacy_value",
    [
        "nousresearch/hermes-agent",
        "ghcr.io/routin/deskclaw-hermes",
    ],
)
@pytest.mark.asyncio
async def test_seed_default_registry_configs_upgrades_legacy_hermes_registry(
    legacy_value,
):
    rows = {
        "image_registry_hermes": SystemConfig(
            key="image_registry_hermes",
            value=legacy_value,
        ),
        "legacy-marker": SystemConfig(key="legacy-marker", value="keep"),
    }
    sessions = []

    def session_factory():
        session = FakeSession(rows)
        sessions.append(session)
        return session

    await _seed_default_registry_configs(session_factory)

    assert (
        rows["image_registry_hermes"].value
        == DEFAULT_REGISTRY_CONFIGS["image_registry_hermes"]
        == "nodesk-center-cn-beijing.cr.volces.com/public/deskclaw-hermes"
    )
    assert rows["image_registry"].value == DEFAULT_REGISTRY_CONFIGS["image_registry"]
    assert (
        rows["image_registry_nanobot"].value
        == DEFAULT_REGISTRY_CONFIGS["image_registry_nanobot"]
    )
    assert rows["legacy-marker"].value == "keep"
    assert sessions[0].commit_count == 1
