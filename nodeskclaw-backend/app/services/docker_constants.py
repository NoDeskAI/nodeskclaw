"""Docker deployment constants."""

from pathlib import Path

DOCKER_BASE_PORT = 13000
DOCKER_DATA_DIR = Path.home() / ".nodeskclaw" / "docker-instances"
