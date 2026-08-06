"""Shared runtime singletons, injected once by graph.build_app().

Agent modules read these as `runtime.llm`, `runtime.tavily`, etc. AT CALL TIME
(attribute access), so they always see the values build_app() set — this avoids
the stale-None problem you'd get from `from .runtime import llm`.
"""
llm = None
llm_with_tools = None
tavily = None
guardrail = None


def init(llm_, llm_with_tools_, tavily_, guardrail_):
    global llm, llm_with_tools, tavily, guardrail
    llm = llm_
    llm_with_tools = llm_with_tools_
    tavily = tavily_
    guardrail = guardrail_
