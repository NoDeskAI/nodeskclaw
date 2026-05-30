import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.models.cluster import Cluster
from app.models.corridor import HumanHex
from app.models.instance import Instance
from app.models.node_card import NodeCard
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_agent import WorkspaceAgent
from app.schemas.workspace import AddAgentRequest, UpdateAgentRequest
from app.services import workspace_service
from app.services import conversation_service
import app.services.corridor_router as corridor_router

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


@pytest.mark.asyncio
async def test_update_agent_syncs_node_card_position(monkeypatch: pytest.MonkeyPatch):
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(corridor_router, "cascade_delete_connections", noop)
    monkeypatch.setattr(corridor_router, "auto_connect_hex", noop)

    async with TestSessionLocal() as db:
        suffix = uuid.uuid4().hex[:8]
        org = Organization(id=f"org-agent-sync-{suffix}", name="Org", slug=f"org-agent-sync-{suffix}")
        user = User(id=f"user-agent-sync-{suffix}", name="Tester", username=f"tester-agent-sync-{suffix}")
        db.add_all([org, user])
        await db.flush()
        cluster = Cluster(
            id=f"cluster-agent-sync-{suffix}",
            name="Cluster",
            org_id=org.id,
            created_by=user.id,
        )
        workspace = Workspace(
            id=f"ws-agent-sync-{suffix}",
            org_id=org.id,
            name="Workspace",
            description="",
            color="#111111",
            icon="bot",
            created_by=user.id,
        )
        instance = Instance(
            id=f"inst-agent-sync-{suffix}",
            name="Agent",
            slug=f"agent-sync-{suffix}",
            cluster_id=cluster.id,
            namespace="default",
            image_version="latest",
            created_by=user.id,
            org_id=org.id,
            workspace_id=workspace.id,
            status="running",
        )
        agent = WorkspaceAgent(
            id=f"wa-agent-sync-{suffix}",
            workspace_id=workspace.id,
            instance_id=instance.id,
            hex_q=1,
            hex_r=0,
            display_name="Agent",
        )
        card = NodeCard(
            id=f"card-agent-sync-{suffix}",
            node_type="agent",
            node_id=instance.id,
            workspace_id=workspace.id,
            hex_q=1,
            hex_r=0,
            name="Agent",
        )
        db.add_all([cluster, workspace, instance, agent, card])
        await db.commit()

        updated = await workspace_service.update_agent(
            db,
            workspace.id,
            instance.id,
            UpdateAgentRequest(hex_q=3, hex_r=-1),
        )

        await db.refresh(card)
        assert updated is not None
        assert updated.hex_q == 3
        assert updated.hex_r == -1
        assert card.hex_q == 3
        assert card.hex_r == -1


@pytest.mark.asyncio
async def test_update_agent_syncs_node_card_name_on_rename(monkeypatch: pytest.MonkeyPatch):
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(corridor_router, "cascade_delete_connections", noop)
    monkeypatch.setattr(corridor_router, "auto_connect_hex", noop)

    async with TestSessionLocal() as db:
        suffix = uuid.uuid4().hex[:8]
        org = Organization(id=f"org-agent-rename-{suffix}", name="Org", slug=f"org-agent-rename-{suffix}")
        user = User(id=f"user-agent-rename-{suffix}", name="Tester", username=f"tester-agent-rename-{suffix}")
        db.add_all([org, user])
        await db.flush()
        cluster = Cluster(
            id=f"cluster-agent-rename-{suffix}",
            name="Cluster",
            org_id=org.id,
            created_by=user.id,
        )
        workspace = Workspace(
            id=f"ws-agent-rename-{suffix}",
            org_id=org.id,
            name="Workspace",
            description="",
            color="#111111",
            icon="bot",
            created_by=user.id,
        )
        instance = Instance(
            id=f"inst-agent-rename-{suffix}",
            name="Agent Origin",
            slug=f"agent-rename-{suffix}",
            cluster_id=cluster.id,
            namespace="default",
            image_version="latest",
            created_by=user.id,
            org_id=org.id,
            workspace_id=workspace.id,
            status="running",
        )
        agent = WorkspaceAgent(
            id=f"wa-agent-rename-{suffix}",
            workspace_id=workspace.id,
            instance_id=instance.id,
            hex_q=1,
            hex_r=0,
            display_name="Agent Origin",
        )
        card = NodeCard(
            id=f"card-agent-rename-{suffix}",
            node_type="agent",
            node_id=instance.id,
            workspace_id=workspace.id,
            hex_q=1,
            hex_r=0,
            name="Agent Origin",
        )
        db.add_all([cluster, workspace, instance, agent, card])
        await db.commit()

        updated = await workspace_service.update_agent(
            db,
            workspace.id,
            instance.id,
            UpdateAgentRequest(display_name="Agent Renamed"),
        )

        await db.refresh(card)
        assert updated is not None
        assert updated.display_name == "Agent Renamed"
        assert card.name == "Agent Renamed"


@pytest.mark.asyncio
async def test_add_agent_auto_position_skips_occupied_node_cards(monkeypatch: pytest.MonkeyPatch):
    async def noop(*args, **kwargs):
        return None

    async def auto_connect(*args, **kwargs):
        return []

    async def has_any_connections(*args, **kwargs):
        return False

    monkeypatch.setattr(corridor_router, "auto_connect_hex", auto_connect)
    monkeypatch.setattr(corridor_router, "has_any_connections", has_any_connections)
    monkeypatch.setattr(conversation_service, "sync_conversations_and_notify_topology", noop)
    monkeypatch.setattr(workspace_service, "_deploy_channel_plugin", noop)
    monkeypatch.setattr(workspace_service, "_broadcast_join_message", noop)
    monkeypatch.setattr(workspace_service, "_send_welcome_message", noop)

    async with TestSessionLocal() as db:
        suffix = uuid.uuid4().hex[:8]
        org = Organization(id=f"org-agent-add-{suffix}", name="Org", slug=f"org-agent-add-{suffix}")
        user = User(id=f"user-agent-add-{suffix}", name="Tester", username=f"tester-agent-add-{suffix}")
        db.add_all([org, user])
        await db.flush()
        cluster = Cluster(
            id=f"cluster-agent-add-{suffix}",
            name="Cluster",
            org_id=org.id,
            created_by=user.id,
        )
        workspace = Workspace(
            id=f"ws-agent-add-{suffix}",
            org_id=org.id,
            name="Workspace",
            description="",
            color="#111111",
            icon="bot",
            created_by=user.id,
            cluster_id=cluster.id,
        )
        existing_instances = [
            Instance(
                id=f"inst-agent-add-{suffix}-{idx}",
                name=f"Agent {idx}",
                slug=f"agent-add-{suffix}-{idx}",
                cluster_id=cluster.id,
                namespace="default",
                image_version="latest",
                created_by=user.id,
                org_id=org.id,
                status="running",
            )
            for idx in range(3)
        ]
        existing_positions = [(1, 0), (1, -1), (0, -1)]
        existing_agents = [
            WorkspaceAgent(
                id=f"wa-agent-add-{suffix}-{idx}",
                workspace_id=workspace.id,
                instance_id=inst.id,
                hex_q=pos[0],
                hex_r=pos[1],
                display_name=inst.name,
            )
            for idx, (inst, pos) in enumerate(zip(existing_instances, existing_positions))
        ]
        existing_cards = [
            NodeCard(
                id=f"card-blackboard-add-{suffix}",
                node_type="blackboard",
                node_id=workspace.id,
                workspace_id=workspace.id,
                hex_q=0,
                hex_r=0,
                name="Blackboard",
            ),
            *[
                NodeCard(
                    id=f"card-agent-add-{suffix}-{idx}",
                    node_type="agent",
                    node_id=inst.id,
                    workspace_id=workspace.id,
                    hex_q=pos[0],
                    hex_r=pos[1],
                    name=inst.name,
                )
                for idx, (inst, pos) in enumerate(zip(existing_instances, existing_positions))
            ],
            NodeCard(
                id=f"card-human-add-{suffix}",
                node_type="human",
                node_id=f"human-agent-add-{suffix}",
                workspace_id=workspace.id,
                hex_q=-1,
                hex_r=0,
                name="Human",
            ),
        ]
        human = HumanHex(
            id=f"human-agent-add-{suffix}",
            workspace_id=workspace.id,
            user_id=user.id,
            hex_q=-1,
            hex_r=0,
            display_name="Human",
            created_by=user.id,
        )
        new_instance = Instance(
            id=f"inst-agent-add-new-{suffix}",
            name="Agent New",
            slug=f"agent-add-new-{suffix}",
            cluster_id=cluster.id,
            namespace="default",
            image_version="latest",
            created_by=user.id,
            org_id=org.id,
            status="running",
        )
        db.add_all([
            cluster, workspace, *existing_instances, *existing_agents,
            *existing_cards, human, new_instance,
        ])
        await db.commit()

        added = await workspace_service.add_agent(
            db,
            workspace.id,
            AddAgentRequest(instance_id=new_instance.id, display_name="Agent New"),
            user.id,
        )

        card_result = await db.execute(
            select(NodeCard).where(NodeCard.node_id == new_instance.id)
        )
        new_card = card_result.scalar_one_or_none()
        assert added.hex_q == -1
        assert added.hex_r == 1
        assert new_card is not None
        assert new_card.hex_q == -1
        assert new_card.hex_r == 1
