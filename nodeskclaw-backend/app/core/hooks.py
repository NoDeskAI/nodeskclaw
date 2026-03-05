"""轻量级同步 Hook 系统 — CE emit，EE 注册 handler。

用于解耦 CE 核心逻辑与 EE 附加行为（如审计日志）。
CE 代码只负责 emit，不关心是否有 handler。
EE 在加载时注册 handler。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

HookHandler = Callable[..., Any]

_handlers: dict[str, list[HookHandler]] = defaultdict(list)


def register(event: str, handler: HookHandler) -> None:
    """注册事件处理函数。"""
    _handlers[event].append(handler)


async def emit(event: str, **kwargs: Any) -> None:
    """触发事件，依次调用所有注册的 handler。"""
    for handler in _handlers.get(event, []):
        try:
            result = handler(**kwargs)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.exception("Hook handler error: event=%s handler=%s", event, handler.__name__)


def clear(event: str | None = None) -> None:
    """清除 handler（测试用）。"""
    if event:
        _handlers.pop(event, None)
    else:
        _handlers.clear()
