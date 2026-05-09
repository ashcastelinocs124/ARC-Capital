"""FigureProfile — qualitative context retrieval for tracked figures.

Mirrors the `agents/personas/` advisor framework but feeds the trigger
system rather than human consultation. Per-figure RAG corpus on disk;
retrieval keyed on the content of the triggering post; consumed by
Stage B (figure-relative confirmation) and the Hypothesis Agent (analogy
+ outcome examples).
"""
