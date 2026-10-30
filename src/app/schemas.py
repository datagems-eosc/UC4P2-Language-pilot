"""Request and response models for the Pilot 2 API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from src.decomposition.modes import FEW_SHOT, normalize_decompose_mode


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    query_id: Optional[str] = None
    include_trace: bool = Field(
        default=False,
        description="If true, also return the raw LangGraph node updates as raw_trace.",
    )
    k: Optional[int] = Field(default=None, ge=1, le=20)
    decompose_mode: str = Field(
        default=FEW_SHOT,
        description=(
            "How the decompose step prompts the LLM: "
            "`predict` (zero-shot DSPy Predict), "
            "`cot` (ChainOfThought), "
            "`few-shot` (Predict with benchmark demonstrations)."
        ),
        examples=["few-shot", "predict", "cot"],
    )
    use_memory: bool = Field(
        default=True,
        description=(
            "If true (default), reuse a stored result for the same question and options "
            "instead of re-running the pipeline."
        ),
    )
    refresh: bool = Field(
        default=False,
        description=(
            "If true, ignore stored memory, run the pipeline again, and overwrite the "
            "stored result. Use this to check consistency across runs."
        ),
    )
    use_extension_questions: bool = Field(
        default=False,
        description=(
            "If true, each knowledge-extension question is retrieved as its own "
            "search. Decomposition still uses the original question. Default is "
            "one search per slice from the QDMR plan."
        ),
    )
    llm_model: Optional[str] = Field(
        default=None,
        description=(
            "Scayle (or configured provider) model for the main pipeline "
            "(synthesize / local extend / local decompose). Default: "
            "SCAYLE_MODEL_NAME / LLM_MODEL / qwen3."
        ),
        examples=["qwen3", "glm-5.3-flash", "kimi-k2.6"],
    )
    judge_llm_model: Optional[str] = Field(
        default=None,
        description=(
            "Scayle model for LLM-as-judge (must differ from llm_model). "
            "Default: JUDGE_LLM_MODEL / glm-5.3-flash."
        ),
        examples=["glm-5.3-flash", "kimi-k2.6", "qwen3"],
    )

    @field_validator("decompose_mode", mode="before")
    @classmethod
    def _decompose_mode(cls, value: Any) -> str:
        try:
            return normalize_decompose_mode(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("llm_model", "judge_llm_model", mode="before")
    @classmethod
    def _optional_model(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ThematicExplorationRequest(QueryRequest):
    until: Optional[str] = Field(
        default=None,
        description=(
            "Stop after this LangGraph node: route, disambiguate, extend_knowledge, "
            "generate_subquestions, decompose, retrieve_slices, compute_features, "
            "synthesize, evaluate_answer, export_benchmark."
        ),
    )


CompareRequest = ThematicExplorationRequest


class PipelineStep(BaseModel):
    """One executed pipeline node and what it produced."""

    step: int
    name: str
    title: str
    outcome: str
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)


class ThematicExplorationResponse(BaseModel):
    service: str = "UC4P2 Language Pilot"
    query_id: str = ""
    question: str
    status: str = Field(
        description="ok, running (SSE only), clarification, partial, timeout, or error."
    )
    last_step: str = ""
    failed_step: Optional[str] = Field(
        default=None,
        description="Pipeline node that timed out or raised when status is timeout/error.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Human-readable failure summary when the run stopped early.",
    )
    result: Optional[PipelineStep] = Field(
        default=None,
        description="The last executed step (the target of a /steps/* call).",
    )
    pipeline: list[PipelineStep] = Field(
        default_factory=list,
        description="Ordered steps with outcome and output so the answer is traceable.",
    )
    clarification: Optional[str] = None
    constraint_errors: list[str] = Field(default_factory=list)
    concept: str = ""
    comparison_type: str = ""
    slices: list[dict[str, Any]] = Field(default_factory=list)
    qdmr: list[dict[str, Any]] = Field(default_factory=list)
    generated_subquestions: list[dict[str, str]] = Field(default_factory=list)
    decompose_mode: str = ""
    use_extension_questions: bool = False
    llm_model: str = ""
    judge_llm_model: str = ""
    search_queries: dict[str, str] = Field(default_factory=dict)
    passages: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    retrieval_errors: dict[str, str] = Field(default_factory=dict)
    feature_metrics: dict[str, Any] = Field(default_factory=dict)
    synthesized_answer: Optional[str] = None
    grounded_citations: list[dict[str, Any]] = Field(default_factory=list)
    nlg_evaluation: dict[str, Any] = Field(default_factory=dict)
    benchmark: Optional[dict[str, Any]] = None
    steps: list[str] = Field(default_factory=list)
    raw_trace: Optional[list[dict[str, Any]]] = None
    memory: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Run-memory metadata: hit=true when served from storage; key/path/stored_at "
            "identify the cached record."
        ),
    )


CompareResponse = ThematicExplorationResponse
