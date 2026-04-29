from __future__ import annotations

from pathlib import Path

from app.services.runtime.config_adapter import HermesConfigAdapter
from app.services.unified_channel_schema import get_channel_schema


class TestHermesConfigAdapter:

    def test_extract_channels_merges_platforms_with_top_level_overrides(self):
        adapter = HermesConfigAdapter()
        config = {
            "platforms": {
                "telegram": {
                    "enabled": True,
                    "token": "tg-token",
                    "extra": {
                        "mention_patterns": ["^bot"],
                    },
                },
                "webhook": {
                    "enabled": True,
                    "extra": {"secret": "keep-me"},
                },
            },
            "telegram": {
                "require_mention": True,
                "free_response_chats": ["12345"],
            },
        }

        channels = adapter.extract_channels(config)

        assert channels == {
            "telegram": {
                "enabled": True,
                "token": "tg-token",
                "extra": {
                    "mention_patterns": ["^bot"],
                    "require_mention": True,
                    "free_response_chats": ["12345"],
                },
            }
        }

    def test_translate_round_trip_preserves_unmapped_fields(self):
        adapter = HermesConfigAdapter()
        native = {
            "enabled": True,
            "token": "discord-token",
            "extra": {
                "require_mention": True,
                "channel_prompts": {"123": "research only"},
            },
        }

        canonical = adapter.translate_from_runtime(native, "discord")

        assert canonical["token"] == "discord-token"
        assert canonical["groupPolicy"] == "mention"
        assert canonical["enabled"] is True
        assert canonical["extra"] == {"channel_prompts": {"123": "research only"}}

        round_trip = adapter.translate_to_runtime(canonical, "discord")
        assert round_trip == native

    def test_merge_channels_preserves_unmanaged_platforms_and_syncs_top_level(self):
        adapter = HermesConfigAdapter()
        config = {
            "platforms": {
                "telegram": {"enabled": True, "token": "old-token"},
                "webhook": {"enabled": True, "extra": {"secret": "keep-me"}},
            },
            "telegram": {
                "require_mention": True,
                "mention_patterns": ["^old"],
            },
        }
        channels = {
            "telegram": {
                "token": "new-token",
                "extra": {
                    "require_mention": False,
                    "mention_patterns": ["^new"],
                },
            }
        }

        merged = adapter.merge_channels(config, channels)

        assert merged["platforms"]["webhook"] == {"enabled": True, "extra": {"secret": "keep-me"}}
        assert merged["platforms"]["telegram"] == {
            "enabled": True,
            "token": "new-token",
            "extra": {
                "require_mention": False,
                "mention_patterns": ["^new"],
            },
        }
        assert merged["telegram"] == {
            "require_mention": False,
            "mention_patterns": ["^new"],
        }

    def test_feishu_group_policy_mention_is_preserved_for_runtime(self):
        adapter = HermesConfigAdapter()

        native = adapter.translate_to_runtime({"groupPolicy": "mention"}, "feishu")

        assert native == {"extra": {"default_group_policy": "mention"}}


class TestHermesChannelSchema:

    def test_telegram_schema_marks_hermes_fields_applicable(self):
        schema = get_channel_schema("telegram", runtime_id="hermes")
        assert schema is not None

        by_key = {field["key"]: field for field in schema}
        assert by_key["botToken"]["applicable"] is True
        assert by_key["groupPolicy"]["applicable"] is True
        assert by_key["proxy"]["applicable"] is False

    def test_slack_schema_remains_unsupported_for_hermes(self):
        schema = get_channel_schema("slack", runtime_id="hermes")
        assert schema is not None
        assert all(field["applicable"] is False for field in schema)


def test_hermes_entrypoint_does_not_downgrade_feishu_mention_policy():
    repo_root = Path(__file__).resolve().parents[2]
    entrypoint = repo_root / "nodeskclaw-artifacts" / "hermes-image" / "docker-entrypoint.sh"

    script = entrypoint.read_text(encoding="utf-8")

    assert 'group_policy = "open"' not in script
    assert '_set_if_missing("FEISHU_GROUP_POLICY", group_policy)' in script
