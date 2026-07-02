from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.nodes import (
    company_discovery_node,
    outreach_writer_node,
    relevance_filter_node,
    research_node,
    synthesis_node,
    verification_node,
)
from app.schemas import LangGraphState, SalesAgentState


def build_sales_agent_graph():
    graph = StateGraph(LangGraphState)
    graph.add_node("company_discovery", company_discovery_node)
    graph.add_node("research", research_node)
    graph.add_node("relevance_filter", relevance_filter_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("outreach_writer", outreach_writer_node)
    graph.add_node("verification", verification_node)

    graph.set_entry_point("company_discovery")
    graph.add_edge("company_discovery", "research")
    graph.add_edge("research", "relevance_filter")
    graph.add_edge("relevance_filter", "synthesis")
    graph.add_edge("synthesis", "outreach_writer")
    graph.add_edge("outreach_writer", "verification")
    graph.add_edge("verification", END)
    return graph.compile()


sales_agent_graph = build_sales_agent_graph()


async def run_graph(initial_state: SalesAgentState) -> SalesAgentState:
    result = await sales_agent_graph.ainvoke(initial_state.model_dump())
    return SalesAgentState(**result)
