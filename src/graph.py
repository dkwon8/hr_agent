"""
Main LangGraph pipeline — wires all phases into a single executable graph.

Flow:
  ingest_resumes → deterministic_filter → cross_validate → llm_judge → generate_output → evaluate_pipeline
"""

from langgraph.graph import StateGraph, START, END

from src.state import PipelineState
from src.nodes.ingestion import ingest_resumes
from src.nodes.deterministic import deterministic_filter
from src.nodes.cross_validation import cross_validate
from src.nodes.llm_judge import llm_judge
from src.nodes.output import generate_output
from src.nodes.evaluation import evaluate_pipeline


def build_pipeline() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("ingest_resumes", ingest_resumes)
    graph.add_node("deterministic_filter", deterministic_filter)
    graph.add_node("cross_validate", cross_validate)
    graph.add_node("llm_judge", llm_judge)
    graph.add_node("generate_output", generate_output)
    graph.add_node("evaluate_pipeline", evaluate_pipeline)

    graph.add_edge(START, "ingest_resumes")
    graph.add_edge("ingest_resumes", "deterministic_filter")
    graph.add_edge("deterministic_filter", "cross_validate")
    graph.add_edge("cross_validate", "llm_judge")
    graph.add_edge("llm_judge", "generate_output")
    graph.add_edge("generate_output", "evaluate_pipeline")
    graph.add_edge("evaluate_pipeline", END)

    return graph.compile()
