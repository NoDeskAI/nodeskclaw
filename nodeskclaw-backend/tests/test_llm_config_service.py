from app.services import llm_config_service


def test_nodeskclaw_tool_names_are_complete() -> None:
    assert llm_config_service.NODESKCLAW_TOOL_NAMES == (
        "nodeskclaw_blackboard",
        "nodeskclaw_topology",
        "nodeskclaw_performance",
        "nodeskclaw_proposals",
        "nodeskclaw_gene_discovery",
        "nodeskclaw_file_download",
        "nodeskclaw_chat_history",
        "nodeskclaw_shared_files",
    )
