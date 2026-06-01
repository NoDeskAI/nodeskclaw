from datetime import timedelta
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.agent_device import AgentDeviceGeneBinding, AgentDeviceGrant, AgentDeviceLease
from app.models.base import not_deleted
from app.models.cluster import Cluster
from app.models.corridor import HexConnection
from app.models.gene import Gene, InstanceGene, InstanceGeneStatus
from app.models.instance import Instance
from app.models.node_card import NodeCard
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_agent import WorkspaceAgent
from app.services import agent_device_service
from app.services.agent_device_provider import ProviderStatus

TEST_DATABASE_URL = "postgresql+asyncpg://nodeskclaw:nodeskclaw@localhost:5432/nodeskclaw_test"
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def require_test_db():
    try:
        async with engine.connect():
            yield
    except Exception:
        pytest.skip("PostgreSQL test database is not available")


async def _noop(*args, **kwargs):
    return None


class _FakeProvider:
    provider_id = "browser.bpilot"

    def status(self):
        return ProviderStatus(status="available")

    async def invoke(self, *, device, actor_agent_id, lease, action, payload):
        return {
            "device_id": device.id,
            "actor_agent_id": actor_agent_id,
            "lease_id": lease.id,
            "action": action,
            "payload": payload,
        }


async def _seed_workspace(db: AsyncSession, suffix: str):
    org = Organization(id=f"org-device-{suffix}", name="Org", slug=f"org-device-{suffix}")
    user = User(id=f"user-device-{suffix}", name="Tester", username=f"tester-device-{suffix}")
    cluster = Cluster(
        id=f"cluster-device-{suffix}",
        name=f"Cluster {suffix}",
        org_id=org.id,
        created_by=user.id,
    )
    workspace = Workspace(
        id=f"ws-device-{suffix}",
        org_id=org.id,
        name="Workspace",
        description="",
        color="#111111",
        icon="bot",
        created_by=user.id,
        cluster_id=cluster.id,
    )
    agent = Instance(
        id=f"inst-device-agent-{suffix}",
        name="Agent",
        slug=f"device-agent-{suffix}",
        cluster_id=cluster.id,
        namespace="default",
        image_version="latest",
        created_by=user.id,
        org_id=org.id,
        workspace_id=workspace.id,
        status="running",
    )
    delegate_agent = Instance(
        id=f"inst-device-delegate-{suffix}",
        name="Delegate",
        slug=f"device-delegate-{suffix}",
        cluster_id=cluster.id,
        namespace="default",
        image_version="latest",
        created_by=user.id,
        org_id=org.id,
        workspace_id=workspace.id,
        status="running",
    )
    workspace_agent = WorkspaceAgent(
        id=f"wa-device-agent-{suffix}",
        workspace_id=workspace.id,
        instance_id=agent.id,
        hex_q=1,
        hex_r=0,
        display_name="Agent",
    )
    delegate_workspace_agent = WorkspaceAgent(
        id=f"wa-device-delegate-{suffix}",
        workspace_id=workspace.id,
        instance_id=delegate_agent.id,
        hex_q=-1,
        hex_r=1,
        display_name="Delegate",
    )
    agent_card = NodeCard(
        id=f"card-device-agent-{suffix}",
        node_type="agent",
        node_id=agent.id,
        workspace_id=workspace.id,
        hex_q=1,
        hex_r=0,
        name="Agent",
    )
    delegate_card = NodeCard(
        id=f"card-device-delegate-{suffix}",
        node_type="agent",
        node_id=delegate_agent.id,
        workspace_id=workspace.id,
        hex_q=-1,
        hex_r=1,
        name="Delegate",
    )
    db.add_all([org, user])
    await db.flush()
    db.add_all([cluster, workspace])
    await db.flush()
    db.add_all([agent, delegate_agent])
    await db.flush()
    db.add_all([workspace_agent, delegate_workspace_agent, agent_card, delegate_card])
    await db.flush()
    return org, user, workspace, agent, delegate_agent


async def _place_available_device(
    monkeypatch: pytest.MonkeyPatch,
    db: AsyncSession,
    workspace: Workspace,
    user: User,
    *,
    display_name: str = "Browser Pilot",
    hex_q: int = 3,
    hex_r: int = 0,
):
    monkeypatch.setattr(agent_device_service.corridor_router, "auto_connect_hex", _noop)
    monkeypatch.setattr(agent_device_service, "_status_for_device", lambda _device: ("available", None))
    return await agent_device_service.create_device(
        db,
        workspace_id=workspace.id,
        preset_id="browser.bpilot.session",
        display_name=display_name,
        hex_q=hex_q,
        hex_r=hex_r,
        config=None,
        metadata=None,
        actor_id=user.id,
        org_id=workspace.org_id,
    )


async def _connect_agent_to_device(db: AsyncSession, workspace: Workspace, agent: Instance, device_id: str):
    corridor_card = NodeCard(
        id=f"card-cor-{workspace.id}",
        node_type="corridor",
        node_id=f"corridor-device-{workspace.id}",
        workspace_id=workspace.id,
        hex_q=2,
        hex_r=0,
        name="Corridor",
    )
    db.add(corridor_card)
    db.add_all([
        HexConnection(
            id=f"conn-a-{workspace.id}",
            workspace_id=workspace.id,
            hex_a_q=1,
            hex_a_r=0,
            hex_b_q=2,
            hex_b_r=0,
            direction="both",
        ),
        HexConnection(
            id=f"conn-b-{workspace.id}",
            workspace_id=workspace.id,
            hex_a_q=2,
            hex_a_r=0,
            hex_b_q=3,
            hex_b_r=0,
            direction="both",
        ),
    ])
    await agent_device_service.create_grant(
        db,
        workspace_id=workspace.id,
        device_id=device_id,
        subject_type="agent",
        subject_id=agent.id,
        scopes=["discover", "lease", "invoke", "delegate"],
        can_delegate=True,
        parent_grant_id=None,
        expires_at=None,
        granted_by_type="user",
        granted_by_id=workspace.created_by,
        org_id=workspace.org_id,
    )
    await db.flush()


async def _seed_workspace_for_existing_agent(
    db: AsyncSession,
    *,
    source_workspace: Workspace,
    agent: Instance,
    suffix: str,
) -> Workspace:
    workspace = Workspace(
        id=f"ws-device-{suffix}",
        org_id=source_workspace.org_id,
        name="Second Workspace",
        description="",
        color="#222222",
        icon="bot",
        created_by=source_workspace.created_by,
        cluster_id=source_workspace.cluster_id,
    )
    workspace_agent = WorkspaceAgent(
        id=f"wa-device-agent-{suffix}",
        workspace_id=workspace.id,
        instance_id=agent.id,
        hex_q=1,
        hex_r=0,
        display_name="Agent",
    )
    agent_card = NodeCard(
        id=f"card-device-agent-{suffix}",
        node_type="agent",
        node_id=agent.id,
        workspace_id=workspace.id,
        hex_q=1,
        hex_r=0,
        name="Agent",
    )
    db.add_all([workspace, workspace_agent, agent_card])
    await db.flush()
    return workspace


@pytest.mark.asyncio
async def test_create_device_registers_node_card_and_blocks_hex(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)
    monkeypatch.setattr(agent_device_service.corridor_router, "auto_connect_hex", _noop)

    async with TestSessionLocal() as db:
        org, user, workspace, _agent, _delegate_agent = await _seed_workspace(db, "create")
        device = await agent_device_service.create_device(
            db,
            workspace_id=workspace.id,
            preset_id="browser.bpilot.session",
            display_name="Browser Pilot",
            hex_q=3,
            hex_r=0,
            config=None,
            metadata={"kind": "browser"},
            actor_id=user.id,
            org_id=org.id,
        )
        await db.flush()

        assert device.status == "provider_unconfigured"
        assert device.status_reason == "bpilot_base_url_missing"
        card = (await db.execute(select(NodeCard).where(NodeCard.node_id == device.id))).scalar_one()
        assert card.node_type == "device"
        assert card.workspace_id == workspace.id
        assert card.hex_q == 3
        assert card.hex_r == 0
        assert card.metadata_["protocol_name"] == "Agent Device"
        assert await agent_device_service.is_hex_occupied(db, workspace_id=workspace.id, hex_q=3, hex_r=0)

        with pytest.raises(ConflictError):
            await agent_device_service.create_device(
                db,
                workspace_id=workspace.id,
                preset_id="browser.bpilot.session",
                display_name="Conflict",
                hex_q=3,
                hex_r=0,
                config=None,
                metadata=None,
                actor_id=user.id,
                org_id=org.id,
            )


@pytest.mark.asyncio
async def test_visibility_requires_topology_and_grant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "visibility")
        device = await _place_available_device(monkeypatch, db, workspace, user)

        no_grant = await agent_device_service.device_visibility(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            agent_id=agent.id,
        )
        assert no_grant["visible"] is False
        assert "topology_required" in no_grant["reasons"]
        assert "grant_missing" in no_grant["reasons"]

        await _connect_agent_to_device(db, workspace, agent, device.id)

        visible = await agent_device_service.device_visibility(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            agent_id=agent.id,
        )
        assert visible["visible"] is True
        assert visible["reachability_source"] == "topology"
        assert visible["grant_id"] is not None


@pytest.mark.asyncio
async def test_exclusive_lease_expires_before_reacquire(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "lease")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        await _connect_agent_to_device(db, workspace, agent, device.id)

        lease = await agent_device_service.acquire_lease(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            agent_id=agent.id,
            ttl_seconds=60,
            org_id=workspace.org_id,
        )
        await db.flush()

        with pytest.raises(ConflictError):
            await agent_device_service.acquire_lease(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                agent_id=agent.id,
                ttl_seconds=60,
                org_id=workspace.org_id,
            )

        lease.expires_at = agent_device_service.utc_now() - timedelta(seconds=1)
        await db.flush()

        replacement = await agent_device_service.acquire_lease(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            agent_id=agent.id,
            ttl_seconds=60,
            org_id=workspace.org_id,
        )
        await db.flush()

        assert lease.status == "expired"
        assert replacement.status == "active"
        assert replacement.id != lease.id


@pytest.mark.asyncio
async def test_lease_requires_available_device(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)
    monkeypatch.setattr(agent_device_service.corridor_router, "auto_connect_hex", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "unavail")
        device = await agent_device_service.create_device(
            db,
            workspace_id=workspace.id,
            preset_id="browser.bpilot.session",
            display_name="Browser Pilot",
            hex_q=3,
            hex_r=0,
            config=None,
            metadata=None,
            actor_id=user.id,
            org_id=workspace.org_id,
        )
        await _connect_agent_to_device(db, workspace, agent, device.id)

        with pytest.raises(BadRequestError):
            await agent_device_service.acquire_lease(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                agent_id=agent.id,
                ttl_seconds=60,
                org_id=workspace.org_id,
            )


@pytest.mark.asyncio
async def test_agent_can_delegate_subset_to_another_agent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, delegate_agent = await _seed_workspace(db, "delegate")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        parent = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=None,
            expires_at=None,
            granted_by_type="user",
            granted_by_id=user.id,
            org_id=workspace.org_id,
        )

        child = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            scopes=["discover", "lease"],
            can_delegate=False,
            parent_grant_id=parent.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=agent.id,
            org_id=workspace.org_id,
        )
        assert child.parent_grant_id == parent.id
        assert child.expires_at is not None

        with pytest.raises(BadRequestError):
            await agent_device_service.create_grant(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                subject_type="human",
                subject_id=user.id,
                scopes=["discover"],
                can_delegate=False,
                parent_grant_id=parent.id,
                expires_at=None,
                granted_by_type="agent",
                granted_by_id=agent.id,
                org_id=workspace.org_id,
            )


@pytest.mark.asyncio
async def test_child_grant_requires_active_parent_chain(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, delegate_agent = await _seed_workspace(db, "parent-chain")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        parent = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=None,
            expires_at=None,
            granted_by_type="user",
            granted_by_id=user.id,
            org_id=workspace.org_id,
        )
        await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            scopes=["discover", "lease"],
            can_delegate=False,
            parent_grant_id=parent.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=agent.id,
            org_id=workspace.org_id,
        )

        parent.revoked_at = agent_device_service.utc_now()
        parent.soft_delete()
        await db.flush()

        assert await agent_device_service.find_valid_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            required_scope="lease",
        ) is None


@pytest.mark.asyncio
async def test_agent_delegation_rejects_invalid_parent_chain(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, delegate_agent = await _seed_workspace(db, "delegate-chain")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        parent = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=None,
            expires_at=None,
            granted_by_type="user",
            granted_by_id=user.id,
            org_id=workspace.org_id,
        )
        await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=parent.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=agent.id,
            org_id=workspace.org_id,
        )
        parent.expires_at = agent_device_service.utc_now() - timedelta(seconds=1)
        await db.flush()

        with pytest.raises(ForbiddenError):
            await agent_device_service.create_grant(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                subject_type="agent",
                subject_id="inst-device-third-delegate-chain",
                scopes=["discover"],
                can_delegate=False,
                parent_grant_id=None,
                expires_at=None,
                granted_by_type="agent",
                granted_by_id=delegate_agent.id,
                org_id=workspace.org_id,
            )


@pytest.mark.asyncio
async def test_revoking_parent_grant_revokes_children_and_reclaims_leases(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, delegate_agent = await _seed_workspace(db, "cascade-revoke")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        parent = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=None,
            expires_at=None,
            granted_by_type="user",
            granted_by_id=user.id,
            org_id=workspace.org_id,
        )
        child = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            scopes=["discover", "lease"],
            can_delegate=False,
            parent_grant_id=parent.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=agent.id,
            org_id=workspace.org_id,
        )
        lease = AgentDeviceLease(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            device_id=device.id,
            holder_agent_id=delegate_agent.id,
            grant_id=child.id,
            status="active",
            expires_at=agent_device_service.utc_now() + timedelta(seconds=60),
        )
        db.add(lease)
        await db.flush()

        await agent_device_service.revoke_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            grant_id=parent.id,
            actor_type="user",
            actor_id=user.id,
            org_id=workspace.org_id,
        )
        await db.flush()

        assert child.revoked_at is not None
        active_child_id = (await db.execute(
            select(AgentDeviceGrant.id).where(
                AgentDeviceGrant.id == child.id,
                not_deleted(AgentDeviceGrant),
            )
        )).scalar_one_or_none()
        assert active_child_id is None
        assert lease.status == "reclaimed"
        assert lease.released_at is not None
        assert await agent_device_service.find_valid_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            required_scope="lease",
        ) is None


@pytest.mark.asyncio
async def test_invoke_requires_active_holder_lease(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)
    monkeypatch.setattr(agent_device_service, "get_agent_device_provider", lambda _provider_id: _FakeProvider())

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "invoke")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        await _connect_agent_to_device(db, workspace, agent, device.id)
        lease = await agent_device_service.acquire_lease(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            agent_id=agent.id,
            ttl_seconds=60,
            org_id=workspace.org_id,
        )

        result = await agent_device_service.invoke_device(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            agent_id=agent.id,
            lease_id=lease.id,
            action="page.goto",
            payload={"url": "https://example.com"},
            org_id=workspace.org_id,
        )
        assert result["status"] == "ok"
        assert result["result"]["action"] == "page.goto"
        assert result["result"]["payload"]["url"] == "https://example.com"

        await agent_device_service.release_lease(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            lease_id=lease.id,
            agent_id=agent.id,
            org_id=workspace.org_id,
        )
        with pytest.raises(NotFoundError):
            await agent_device_service.invoke_device(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                agent_id=agent.id,
                lease_id=lease.id,
                action="page.goto",
                payload={},
                org_id=workspace.org_id,
            )


@pytest.mark.asyncio
async def test_agent_reclaim_requires_own_or_ancestor_delegation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, delegate_agent = await _seed_workspace(db, "reclaim")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        parent = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=None,
            expires_at=None,
            granted_by_type="user",
            granted_by_id=user.id,
            org_id=workspace.org_id,
        )
        child = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            scopes=["discover", "lease"],
            can_delegate=False,
            parent_grant_id=parent.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=agent.id,
            org_id=workspace.org_id,
        )
        lease = AgentDeviceLease(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            device_id=device.id,
            holder_agent_id=delegate_agent.id,
            grant_id=child.id,
            status="active",
            expires_at=agent_device_service.utc_now() + timedelta(seconds=60),
        )
        db.add(lease)
        await db.flush()

        reclaimed = await agent_device_service.reclaim_lease(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            lease_id=lease.id,
            actor_type="agent",
            actor_id=agent.id,
            org_id=workspace.org_id,
        )
        assert reclaimed.status == "reclaimed"
        await db.flush()

        parent_lease = AgentDeviceLease(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            device_id=device.id,
            holder_agent_id=agent.id,
            grant_id=parent.id,
            status="active",
            expires_at=agent_device_service.utc_now() + timedelta(seconds=60),
        )
        db.add(parent_lease)
        await db.flush()

        with pytest.raises(ForbiddenError):
            await agent_device_service.reclaim_lease(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                lease_id=parent_lease.id,
                actor_type="agent",
                actor_id=delegate_agent.id,
                org_id=workspace.org_id,
            )


@pytest.mark.asyncio
async def test_agent_reclaim_rejects_invalid_parent_chain(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, delegate_agent = await _seed_workspace(db, "reclaim-chain")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        parent = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=None,
            expires_at=None,
            granted_by_type="user",
            granted_by_id=user.id,
            org_id=workspace.org_id,
        )
        child = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id=delegate_agent.id,
            scopes=["discover", "lease", "invoke", "delegate"],
            can_delegate=True,
            parent_grant_id=parent.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=agent.id,
            org_id=workspace.org_id,
        )
        grandchild = await agent_device_service.create_grant(
            db,
            workspace_id=workspace.id,
            device_id=device.id,
            subject_type="agent",
            subject_id="inst-device-worker-reclaim-chain",
            scopes=["lease"],
            can_delegate=False,
            parent_grant_id=child.id,
            expires_at=None,
            granted_by_type="agent",
            granted_by_id=delegate_agent.id,
            org_id=workspace.org_id,
        )
        lease = AgentDeviceLease(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            device_id=device.id,
            holder_agent_id=grandchild.subject_id,
            grant_id=grandchild.id,
            status="active",
            expires_at=agent_device_service.utc_now() + timedelta(seconds=60),
        )
        db.add(lease)
        parent.expires_at = agent_device_service.utc_now() - timedelta(seconds=1)
        await db.flush()

        with pytest.raises(ForbiddenError):
            await agent_device_service.reclaim_lease(
                db,
                workspace_id=workspace.id,
                device_id=device.id,
                lease_id=lease.id,
                actor_type="agent",
                actor_id=delegate_agent.id,
                org_id=workspace.org_id,
            )


@pytest.mark.asyncio
async def test_withdraw_gene_binding_keeps_shared_auto_gene_until_last_device(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    from app.services import gene_service

    uninstall_calls = []

    async def fake_uninstall_gene(db: AsyncSession, instance_id: str, gene_id: str):
        uninstall_calls.append((instance_id, gene_id))

    monkeypatch.setattr(gene_service, "uninstall_gene", fake_uninstall_gene)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "gene-shared")
        first_device = await _place_available_device(
            monkeypatch,
            db,
            workspace,
            user,
            display_name="Browser Pilot A",
            hex_q=3,
            hex_r=0,
        )
        second_device = await _place_available_device(
            monkeypatch,
            db,
            workspace,
            user,
            display_name="Browser Pilot B",
            hex_q=4,
            hex_r=0,
        )
        gene = Gene(
            id="gene-agent-device-browser-bpilot",
            name="Agent Device Browser Pilot",
            slug="agent-device-browser-bpilot",
            description="",
            short_description="",
            category="agent-device",
        )
        instance_gene = InstanceGene(
            id="ig-agent-device-browser-bpilot",
            instance_id=agent.id,
            gene_id=gene.id,
            status=InstanceGeneStatus.installed,
            installed_version="1.0.0",
        )
        db.add_all([gene, instance_gene])
        await db.flush()
        db.add(AgentDeviceGeneBinding(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            device_id=first_device.id,
            instance_id=agent.id,
            gene_id=gene.id,
            gene_slug=gene.slug,
            instance_gene_id=instance_gene.id,
            was_preexisting=False,
            sync_reason="test",
        ))
        await db.flush()
        await agent_device_service.ensure_gene_binding(
            db,
            workspace_id=workspace.id,
            device=second_device,
            instance=agent,
            gene_slug=gene.slug,
            reason="topology_sync",
        )
        await db.flush()

        second_binding = (await db.execute(
            select(AgentDeviceGeneBinding).where(
                AgentDeviceGeneBinding.device_id == second_device.id,
                AgentDeviceGeneBinding.deleted_at.is_(None),
            )
        )).scalar_one()
        assert second_binding.was_preexisting is False

        await agent_device_service.withdraw_gene_binding(
            db,
            workspace_id=workspace.id,
            device=first_device,
            instance=agent,
            gene_slug=gene.slug,
            reason="device_deleted",
        )
        await db.flush()

        assert uninstall_calls == []
        second_binding = (await db.execute(
            select(AgentDeviceGeneBinding).where(
                AgentDeviceGeneBinding.device_id == second_device.id,
                AgentDeviceGeneBinding.deleted_at.is_(None),
            )
        )).scalar_one()
        assert second_binding.sync_reason == "topology_sync"

        await agent_device_service.withdraw_gene_binding(
            db,
            workspace_id=workspace.id,
            device=second_device,
            instance=agent,
            gene_slug=gene.slug,
            reason="device_deleted",
        )
        await db.flush()

        assert uninstall_calls == [(agent.id, gene.id)]


@pytest.mark.asyncio
async def test_ensure_gene_binding_skips_binding_when_auto_install_fails(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    from app.services import gene_service

    async def fake_install_gene_prerestart(instance_id: str, gene_slug: str):
        raise RuntimeError(f"install failed for {instance_id}:{gene_slug}")

    monkeypatch.setattr(gene_service, "install_gene_prerestart", fake_install_gene_prerestart)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "gene-fail")
        device = await _place_available_device(monkeypatch, db, workspace, user)
        gene = Gene(
            id="gene-agent-device-install-fail",
            name="Agent Device Install Fail",
            slug="agent-device-browser-bpilot",
            description="",
            short_description="",
            category="agent-device",
        )
        db.add(gene)
        await db.flush()

        await agent_device_service.ensure_gene_binding(
            db,
            workspace_id=workspace.id,
            device=device,
            instance=agent,
            gene_slug=gene.slug,
            reason="topology_sync",
        )
        await db.flush()

        binding_id = (await db.execute(
            select(AgentDeviceGeneBinding.id).where(
                AgentDeviceGeneBinding.device_id == device.id,
                not_deleted(AgentDeviceGeneBinding),
            )
        )).scalar_one_or_none()
        assert binding_id is None


@pytest.mark.asyncio
async def test_withdraw_workspace_agent_bindings_preserves_gene_used_by_other_workspace(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(agent_device_service.hooks, "emit", _noop)

    from app.services import gene_service

    uninstall_calls = []

    async def fake_uninstall_gene(db: AsyncSession, instance_id: str, gene_id: str):
        uninstall_calls.append((instance_id, gene_id))

    monkeypatch.setattr(gene_service, "uninstall_gene", fake_uninstall_gene)

    async with TestSessionLocal() as db:
        _org, user, workspace, agent, _delegate_agent = await _seed_workspace(db, "gene-cross")
        other_workspace = await _seed_workspace_for_existing_agent(
            db,
            source_workspace=workspace,
            agent=agent,
            suffix="gene-cross-other",
        )
        first_device = await _place_available_device(
            monkeypatch,
            db,
            workspace,
            user,
            display_name="Browser Pilot A",
            hex_q=3,
            hex_r=0,
        )
        second_device = await _place_available_device(
            monkeypatch,
            db,
            other_workspace,
            user,
            display_name="Browser Pilot B",
            hex_q=3,
            hex_r=0,
        )
        gene = Gene(
            id="gene-bpilot-cross",
            name="Agent Device Browser Pilot Cross",
            slug="agent-device-browser-bpilot",
            description="",
            short_description="",
            category="agent-device",
        )
        instance_gene = InstanceGene(
            id="ig-bpilot-cross",
            instance_id=agent.id,
            gene_id=gene.id,
            status=InstanceGeneStatus.installed,
            installed_version="1.0.0",
        )
        db.add_all([gene, instance_gene])
        await db.flush()
        db.add(AgentDeviceGeneBinding(
            id=str(uuid.uuid4()),
            workspace_id=workspace.id,
            device_id=first_device.id,
            instance_id=agent.id,
            gene_id=gene.id,
            gene_slug=gene.slug,
            instance_gene_id=instance_gene.id,
            was_preexisting=False,
            sync_reason="test",
        ))
        await db.flush()

        await agent_device_service.ensure_gene_binding(
            db,
            workspace_id=other_workspace.id,
            device=second_device,
            instance=agent,
            gene_slug=gene.slug,
            reason="topology_sync",
        )
        await db.flush()

        second_binding = (await db.execute(
            select(AgentDeviceGeneBinding).where(
                AgentDeviceGeneBinding.device_id == second_device.id,
                not_deleted(AgentDeviceGeneBinding),
            )
        )).scalar_one()
        assert second_binding.was_preexisting is False

        await agent_device_service.withdraw_workspace_agent_device_gene_bindings(
            db,
            workspace_id=workspace.id,
            instance_id=agent.id,
            reason="agent_removed",
        )
        await db.flush()

        active_first_binding_id = (await db.execute(
            select(AgentDeviceGeneBinding.id).where(
                AgentDeviceGeneBinding.device_id == first_device.id,
                not_deleted(AgentDeviceGeneBinding),
            )
        )).scalar_one_or_none()
        active_second_binding_id = (await db.execute(
            select(AgentDeviceGeneBinding.id).where(
                AgentDeviceGeneBinding.device_id == second_device.id,
                not_deleted(AgentDeviceGeneBinding),
            )
        )).scalar_one_or_none()
        assert active_first_binding_id is None
        assert active_second_binding_id == second_binding.id
        assert uninstall_calls == []

        await agent_device_service.withdraw_workspace_agent_device_gene_bindings(
            db,
            workspace_id=other_workspace.id,
            instance_id=agent.id,
            reason="agent_removed",
        )
        await db.flush()

        assert uninstall_calls == [(agent.id, gene.id)]
