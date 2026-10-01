"""Scripted-model tests for the lineage agent."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from lineagelens.agent.graph import answer, complete
from lineagelens.project import build_project

WAREHOUSE = Path("tests/fixtures/warehouse")
_CITATION = re.compile(r"[\w./-]+\.\w+:\d+")


class ScriptedModel(FakeMessagesListChatModel):
    """Returns predetermined tool calls, then a final answer. No network."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        response = self.responses[self.i]
        if self.i < len(self.responses) - 1:
            self.i += 1
        return ChatResult(generations=[ChatGeneration(message=response)])


def _tools_called(messages: list[BaseMessage]) -> list[str]:
    names: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            names.extend(call["name"] for call in message.tool_calls)
    return names


def test_scripted_agent_cites_only_tool_evidence() -> None:
    graph = build_project([WAREHOUSE])
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "impact_of_drop",
                        "args": {"column": "raw.orders.status"},
                        "id": "call-drop",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "explain_path",
                        "args": {
                            "source": "raw.orders.status",
                            "destination": "staging.stg_orders.amount",
                        },
                        "id": "call-path",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content=(
                    "Dropping raw.orders.status will break 01_stg_orders.sql:1. "
                    "That edge reaches staging.stg_orders.amount."
                )
            ),
        ]
    )
    typed = complete(graph, "what breaks?", model=model)
    assert _tools_called(typed) == ["impact_of_drop", "explain_path"]
    tool_text = "\n".join(
        message.content
        for message in typed
        if isinstance(message, ToolMessage) and isinstance(message.content, str)
    )
    final = typed[-1].content
    assert isinstance(final, str)
    citations = _CITATION.findall(final)
    assert citations
    assert all(citation in tool_text for citation in citations)
    assert "will break" in final


def test_unknown_column_is_reported() -> None:
    graph = build_project([WAREHOUSE])
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_columns",
                        "args": {"query": "does.not.exist"},
                        "id": "call-search",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="No column found matching does.not.exist."),
        ]
    )
    text = answer(graph, "where is does.not.exist?", model=model)
    assert "No column found" in text
    assert _CITATION.findall(text) == []
