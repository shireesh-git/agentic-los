"""
Agentic framework: the parallel agent graph, tools, structured LLM agents and the critic.

    graph.py    AgentGraph — dependency-ordered, parallel execution with fan-out
    tools.py    typed, permissioned, audited tools agents may call
    runtime.py  LLMAgent — a bounded reason → tool → observe loop over structured output
    critic.py   checks agent output (figures, evidence) before a person sees it
    schema.py   the JSON-schema subset used to validate model output and tool arguments
"""
