from app.services.runtime.messaging.ingestion.portal import build_portal_envelope


def test_build_portal_envelope_promotes_mentions_to_routing_targets() -> None:
    envelope = build_portal_envelope(
        workspace_id="ws-1",
        user_id="user-1",
        user_name="Admin",
        content="hello",
        mentions=["agent-1"],
    )

    assert envelope.data is not None
    assert envelope.data.mentions == ["agent-1"]
    assert envelope.data.routing.mode == "unicast"
    assert envelope.data.routing.targets == ["agent-1"]


def test_build_portal_envelope_defaults_to_multicast_without_mentions() -> None:
    envelope = build_portal_envelope(
        workspace_id="ws-1",
        user_id="user-1",
        user_name="Admin",
        content="hello",
    )

    assert envelope.data is not None
    assert envelope.data.routing.mode == "multicast"
    assert envelope.data.routing.targets == []
