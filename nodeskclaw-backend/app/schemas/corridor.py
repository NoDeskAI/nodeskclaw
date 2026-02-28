"""Pydantic schemas for Corridor system — CorridorHex, HexConnection, Topology, Human Hex."""

from datetime import datetime

from pydantic import BaseModel


class CorridorHexCreate(BaseModel):
    hex_q: int
    hex_r: int
    display_name: str = ""


class CorridorHexUpdate(BaseModel):
    display_name: str | None = None
    hex_q: int | None = None
    hex_r: int | None = None


class CorridorHexInfo(BaseModel):
    id: str
    workspace_id: str
    hex_q: int
    hex_r: int
    display_name: str
    created_by: str | None
    created_at: datetime


class ConnectionCreate(BaseModel):
    hex_a_q: int
    hex_a_r: int
    hex_b_q: int
    hex_b_r: int


class ConnectionInfo(BaseModel):
    id: str
    workspace_id: str
    hex_a_q: int
    hex_a_r: int
    hex_b_q: int
    hex_b_r: int
    auto_created: bool
    created_by: str | None
    created_at: datetime


class HumanHexCreate(BaseModel):
    user_id: str
    hex_q: int
    hex_r: int
    display_color: str = "#f59e0b"
    channel_type: str | None = None
    channel_config: dict | None = None


class HumanHexUpdate(BaseModel):
    hex_q: int | None = None
    hex_r: int | None = None
    display_color: str | None = None
    channel_type: str | None = None
    channel_config: dict | None = None


class HumanHexInfo(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    hex_q: int
    hex_r: int
    display_color: str
    channel_type: str | None = None
    channel_config: dict | None = None
    created_at: datetime


class TopologyNodeInfo(BaseModel):
    hex_q: int
    hex_r: int
    node_type: str
    entity_id: str | None = None
    display_name: str | None = None
    extra: dict = {}


class TopologyEdgeInfo(BaseModel):
    a_q: int
    a_r: int
    b_q: int
    b_r: int
    auto_created: bool


class TopologyInfo(BaseModel):
    nodes: list[TopologyNodeInfo]
    edges: list[TopologyEdgeInfo]
