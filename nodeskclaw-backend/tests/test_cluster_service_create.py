"""create_cluster 集群类型校验测试。"""

import pytest

from app.core.exceptions import BadRequestError
from app.schemas.cluster import ClusterCreate
from app.services.cluster_service import create_cluster


async def test_create_cluster_rejects_docker_compute_provider():
    data = ClusterCreate(name="local-docker", compute_provider="docker")
    with pytest.raises(BadRequestError) as exc_info:
        await create_cluster(data, user=None, db=None)
    assert exc_info.value.message_key == "errors.cluster.compute_provider_not_supported"


async def test_create_cluster_rejects_unknown_compute_provider():
    data = ClusterCreate(name="demo", compute_provider="process")
    with pytest.raises(BadRequestError) as exc_info:
        await create_cluster(data, user=None, db=None)
    assert exc_info.value.message_key == "errors.cluster.compute_provider_not_supported"
