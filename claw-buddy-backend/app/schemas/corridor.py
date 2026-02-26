"""Pydantic schemas for Corridor system — CorridorHex, HexConnection, Topology, Human Hex."""

from datetime import datetime

from pydantic import BaseModel, Field


class CorridorHexCreate(BaseModel):
    hex_q: int
    hex_r: int
    display_name: str = ""


class CorridorHexUpdate(BaseModel):
    display_name: str


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
    direction: str = Field(default="both", pattern=r"^(both|a_to_b|b_to_a)$")


class ConnectionUpdate(BaseModel):
    direction: str = Field(pattern=r"^(both|a_to_b|b_to_a)$")


class ConnectionInfo(BaseModel):
    id: str
    workspace_id: str
    hex_a_q: int
    hex_a_r: int
    hex_b_q: int
    hex_b_r: int
    direction: str
    auto_created: bool
    created_by: str | None
    created_at: datetime


class HumanHexUpdate(BaseModel):
    hex_q: int
    hex_r: int


class HumanChannelUpdate(BaseModel):
    channel_type: str = Field(max_length=20)
    channel_config: dict = {}


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
    direction: str
    auto_created: bool


class TopologyInfo(BaseModel):
    nodes: list[TopologyNodeInfo]
    edges: list[TopologyEdgeInfo]
