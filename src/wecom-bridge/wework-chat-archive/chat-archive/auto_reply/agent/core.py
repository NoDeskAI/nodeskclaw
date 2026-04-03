from __future__ import annotations

import json
import logging

import httpx

from database import get_setting
from config import LLM_API_URL, LLM_API_KEY, LLM_MODEL
from .base_skill import BaseSkill
from .context import context_store

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5
LLM_TIMEOUT = 60

# Appended to the system prompt in group-chat contexts so the LLM knows how
# to interpret [用户名] tags and [截图] markers stored in conversation history.
GROUP_CONTEXT_SUPPLEMENT = """
群聊中的消息带有 [用户名] 前缀标记，上下文中带 [截图] 标记的是用户之前发送的截图的文字描述。

当用户 @你 提问时：
1. 优先关注该用户自己发送的消息和截图（通过 [用户名] 匹配）
2. 如果其他用户的消息与当前问题相关，也可以参考
3. 结合截图描述理解问题全貌
回复时简洁清晰，直接针对提问者的问题。"""


def _cfg(key: str, fallback: str = "") -> str:
    return get_setting(key, fallback)


async def _call_llm(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = "",
) -> dict:
    api_url = _cfg("llm_api_url", LLM_API_URL)
    api_key = _cfg("llm_api_key", LLM_API_KEY)
    use_model = model or _cfg("llm_model", LLM_MODEL)

    if not api_url or not api_key:
        raise ValueError("LLM 未配置 (api_url / api_key)")

    body: dict = {
        "model": use_model,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        resp = await client.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def run_agent(
    conversation_id: str,
    user_message: str,
    system_prompt: str,
    skills: list[BaseSkill],
    model: str = "",
    sender_name: str = "",
) -> tuple[str, str]:
    """Execute the ReAct agent loop.

    Returns (reply_text, skill_name_used).
    """
    tagged_message = f"[{sender_name}] {user_message}" if sender_name else user_message

    effective_prompt = system_prompt
    if sender_name:
        effective_prompt = (system_prompt or "") + GROUP_CONTEXT_SUPPLEMENT

    tools = [s.to_function_schema() for s in skills] if skills else None
    messages = context_store.build_messages(
        conversation_id, effective_prompt, tagged_message,
    )

    skill_used = ""
    choice: dict = {}

    for iteration in range(MAX_ITERATIONS):
        logger.info(
            "[agent] iter=%d msgs=%d tools=%d",
            iteration + 1,
            len(messages),
            len(tools) if tools else 0,
        )

        result = await _call_llm(messages, tools, model)
        choice = result["choices"][0]["message"]

        tool_calls = choice.get("tool_calls")
        if not tool_calls:
            reply = choice.get("content", "").strip() or "..."
            context_store.add(conversation_id, "user", tagged_message)
            context_store.add(conversation_id, "assistant", reply)
            return reply, skill_used

        messages.append(choice)

        for tc in tool_calls:
            fn = tc["function"]
            skill_name = fn["name"]

            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info("[agent] skill call: %s(%s)", skill_name, args)

            skill = next((s for s in skills if s.name == skill_name), None)
            if skill:
                try:
                    sr = await skill.execute(**args)
                    tool_result = sr.content
                    skill_used = skill_name
                except Exception as e:
                    logger.error("[agent] skill %s error: %s", skill_name, e)
                    tool_result = f"Error executing skill: {e}"
            else:
                tool_result = f"Unknown skill: {skill_name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": tool_result,
            })

    final = choice.get("content", "").strip() if choice else ""
    reply = final or "抱歉，我暂时无法回答这个问题。"
    context_store.add(conversation_id, "user", tagged_message)
    context_store.add(conversation_id, "assistant", reply)
    return reply, skill_used
