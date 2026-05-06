from app.services.deploy_service import _rewrite_docker_callback_url


def test_rewrite_docker_callback_url_rewrites_docker_desktop_host() -> None:
    assert _rewrite_docker_callback_url("http://172.17.0.1:4510/api/v1") == "http://host.docker.internal:4510/api/v1"
    assert _rewrite_docker_callback_url("ws://172.17.0.1:4510/api/v1/tunnel/connect") == "ws://host.docker.internal:4510/api/v1/tunnel/connect"


def test_rewrite_docker_callback_url_leaves_remote_host_untouched() -> None:
    assert _rewrite_docker_callback_url("https://nodeskclaw.example.com/api/v1") == "https://nodeskclaw.example.com/api/v1"
