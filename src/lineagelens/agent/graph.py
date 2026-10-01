"""LangGraph ReAct agent over the lineage tools."""

from __future__ import annotations

import os
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from lineagelens.agent.tools import build_tools
from lineagelens.graph import LineageGraph

_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system.md"


def system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def default_model() -> BaseChatModel:
    """Build the chat model named by LINEAGELENS_MODEL, defaulting to OpenAI."""
    from langchain.chat_models import init_chat_model

    model = init_chat_model(os.environ.get("LINEAGELENS_MODEL", "openai:gpt-4.1-mini"))
    if not isinstance(model, BaseChatModel):
        message = "LINEAGELENS_MODEL did not resolve to a chat model."
        raise TypeError(message)
    return model


def complete(
    graph: LineageGraph, question: str, model: BaseChatModel | None = None
) -> list[BaseMessage]:
    """Run the ReAct agent and return the message trace."""
    agent = create_agent(
        model or default_model(),
        build_tools(graph),
        system_prompt=system_prompt(),
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    messages = result["messages"]
    if not isinstance(messages, list):
        return []
    return [message for message in messages if isinstance(message, BaseMessage)]


def answer(graph: LineageGraph, question: str, model: BaseChatModel | None = None) -> str:
    """Answer one question from tool results only."""
    messages = complete(graph, question, model)
    if not messages:
        return ""
    content = messages[-1].content
    return content if isinstance(content, str) else ""
