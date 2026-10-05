"""End-to-end historical comparative question answering.

Disambiguation goes through the query-disambiguation language API.
Retrieval goes through Cross-Dataset Discovery, one search per slice.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import dspy

from src.analytics.feature_engine import attach_corpus_analysis, compute_feature_metrics
from src.constraints.comparative import (
    DisambiguationAPIError,
    QueryDisambiguationClient,
)
from src.decomposition.qdmr_generator import decompose_question
from src.decomposition.modes import FEW_SHOT
from src.knowledge_extension.expander import expand_knowledge, knowledge_extension_payload
from src.orchestration.slice_executor import RetrievalAPIError
from src.retrieval.corpora import corpus_name_for_id, dataset_ids_for_slice
from src.retrieval.multi_slice_retriever import (
    CrossDatasetMultiSliceRetriever,
    MockMultiSliceRetriever,
    RetrievedPassage,
)
from src.schemas.benchmark import BenchmarkOutput, Citation
from src.schemas.slice import ComparisonSlice, ParsedQueryIntent, parse_query_intent, slices_from_disambiguation
from src.schemas.state import PipelineState


class GroundedSynthesizer(dspy.Signature):
    """Write a comparison using ONLY the retrieved passages below.

    Every factual sentence must include one or more [ref_id] markers from the
    evidence. Do not use outside knowledge. If a slice has no passages, say that
    retrieval returned nothing for that slice. Never invent a contrast for a
    slice with no evidence.
    """

    question: str = dspy.InputField()
    evidence: str = dspy.InputField(desc="Retrieved passages, each prefixed with [ref_id], slice, and corpus")
    answer: str = dspy.OutputField(desc="Grounded comparison; claims marked with [ref_id]")


def _query_id(question: str) -> str:
    return "p2-" + hashlib.sha1(question.encode("utf-8")).hexdigest()[:10]


def _dimension_name(comparison_type: str | None) -> str:
    if comparison_type == "cross_lingual":
        return "cross-lingual"
    if comparison_type in {"multi-dimensional", "multi_dimensional"}:
        return "multi-dimensional"
    return "temporal"


def _clarification(errors: list[str]) -> str:
    return (
        "This historical comparative query cannot be executed against the indexed archives. "
        + " ".join(errors)
        + " Please name the concept and restrict every slice to indexed sources from 1800 onward."
    )


def _variants(expansion: dict[str, Any], slices: list[ComparisonSlice]) -> dict[str, list[str]]:
    variants: dict[str, list[str]] = {}
    for slice_ in slices:
        words = expansion.get(slice_.slice_id) or []
        variants[slice_.slice_id] = [str(word) for word in words]
    return variants


_REF = re.compile(r"\[(ref_\d+)\]")
_SNIPPET = 500


def _citation_ids_in(text: str) -> set[str]:
    return set(_REF.findall(text or ""))


def _answer_is_grounded(
    answer: str,
    citations: list[Citation],
    empty_labels: list[str],
) -> bool:
    """True when every [ref_N] exists and empty slices are not fabricated."""
    if not answer.strip():
        return False
    allowed = {item.citation_id for item in citations}
    used = _citation_ids_in(answer)
    if allowed and not used:
        return False
    if used - allowed:
        return False
    lowered = answer.lower()
    for label in empty_labels:
        if not label:
            continue
        if label.lower() in lowered and "no indexed passage" not in lowered and "no retrieved" not in lowered:
            return False
    return True


def _mark_used(citations: list[Citation], answer: str) -> list[Citation]:
    used = _citation_ids_in(answer)
    return [item.model_copy(update={"used_in_answer": item.citation_id in used}) for item in citations]


def _evidence_block(citations: list[Citation]) -> str:
    lines = []
    for item in citations:
        corpus = item.corpus_name or item.dataset_id or "retrieved"
        lines.append(
            f"[{item.citation_id}] slice={item.slice_id} ({item.slice_label}) "
            f"corpus={corpus} doc={item.source_document}\n{item.text_snippet}"
        )
    return "\n\n".join(lines)


def _synthesize_text(
    intent: ParsedQueryIntent,
    passages: dict[str, list[RetrievedPassage]],
    citations: list[Citation],
) -> str:
    by_slice: dict[str, list[Citation]] = {}
    for citation in citations:
        by_slice.setdefault(citation.slice_id, []).append(citation)
    sentences = [
        f"Comparing {intent.target_concept} across {len(intent.slices)} slices ({intent.dimension})."
    ]
    for slice_ in intent.slices:
        refs = by_slice.get(slice_.slice_id) or []
        if not refs:
            sentences.append(f"{slice_.label}: no indexed passage was returned.")
            continue
        marker = " ".join(f"[{item.citation_id}]" for item in refs[:2])
        sentences.append(f"{slice_.label}: {refs[0].text_snippet} {marker}")
    return " ".join(sentences)


class HistoricalQAOrchestrator(dspy.Module):
    """Parse, extend, decompose, retrieve, measure, and synthesize an N-way comparison."""

    def __init__(
        self,
        disambiguation_client: QueryDisambiguationClient | None = None,
        retriever: CrossDatasetMultiSliceRetriever | MockMultiSliceRetriever | None = None,
        decompose_mode: str = FEW_SHOT,
    ):
        super().__init__()
        self.disambiguation_client = disambiguation_client or QueryDisambiguationClient()
        self.retriever = retriever or CrossDatasetMultiSliceRetriever()
        self.decompose_mode = decompose_mode

    def resolve(self, question: str, query_id: str | None = None) -> PipelineState:
        identifier = query_id or _query_id(question)
        try:
            remote = self.disambiguation_client.disambiguate_language(question)
            source = "query-disambiguation-api"
        except DisambiguationAPIError as exc:
            intent, errors = parse_query_intent(question)
            if errors or intent is None:
                return PipelineState(
                    question=question,
                    query_id=identifier,
                    status="clarification",
                    disambiguation_source="local-fallback",
                    clarification=_clarification(errors),
                    constraint_errors=errors,
                    disambiguation={"fallback_reason": str(exc), "proceed": False},
                )
            return PipelineState(
                question=question,
                query_id=identifier,
                status="disambiguated",
                intent=intent,
                disambiguation_source="local-fallback",
                disambiguation={"proceed": True, "fallback_reason": str(exc)},
            )
        if not remote.get("proceed"):
            local_intent, errors = parse_query_intent(question)
            if local_intent is not None:
                merged = dict(remote)
                merged["proceed"] = True
                merged["fallback_reason"] = (
                    "No explicit time period in the query; slices defaulted to indexed corpus eras."
                )
                return PipelineState(
                    question=question,
                    query_id=identifier,
                    status="disambiguated",
                    intent=local_intent,
                    disambiguation=merged,
                    disambiguation_source="local-fallback",
                )
            errors = list(remote.get("constraint_errors") or errors)
            return PipelineState(
                question=question,
                query_id=identifier,
                status="clarification",
                disambiguation=remote,
                disambiguation_source=source,
                clarification=str(remote.get("clarification") or _clarification(errors)),
                constraint_errors=errors,
            )
        slices = slices_from_disambiguation(remote)
        if len(slices) < 2:
            local_intent, errors = parse_query_intent(question)
            if local_intent is None:
                return PipelineState(
                    question=question,
                    query_id=identifier,
                    status="clarification",
                    disambiguation=remote,
                    disambiguation_source=source,
                    clarification=_clarification(errors),
                    constraint_errors=errors,
                )
            intent = local_intent
        else:
            concepts = list(remote.get("target_concepts") or [])
            intent = ParsedQueryIntent(
                original_query=question,
                target_concept=str(concepts[0] if concepts else ""),
                dimension=_dimension_name(remote.get("comparison_type")),
                slices=slices,
            )
        return PipelineState(
            question=question,
            query_id=identifier,
            status="disambiguated",
            intent=intent,
            disambiguation=remote,
            disambiguation_source=source,
        )

    def extend(self, state: PipelineState) -> PipelineState:
        intent = state.intent
        assert intent is not None
        expansion = expand_knowledge(state.question, intent.target_concept, intent.slices)
        state.knowledge_extension = knowledge_extension_payload(expansion)
        state.status = "expanded"
        return state

    def decompose(self, state: PipelineState) -> PipelineState:
        intent = state.intent
        assert intent is not None
        context = intent.target_concept or "the subject"
        state.sub_tasks = decompose_question(
            state.question, intent.slices, context, decompose_mode=self.decompose_mode
        )
        state.decompose_mode = self.decompose_mode
        state.status = "decomposed"
        return state

    def retrieve(self, state: PipelineState) -> PipelineState:
        intent = state.intent
        assert intent is not None
        expansion = dict(state.knowledge_extension)
        passages, errors, queries = self.retriever.retrieve_all(
            intent.target_concept,
            intent.slices,
            _variants(expansion, intent.slices),
            state.sub_tasks,
        )
        state.passages = {
            slice_id: [item.model_dump() for item in items] for slice_id, items in passages.items()
        }
        state.retrieval_errors = errors
        state.search_queries = queries
        state.status = "retrieved"
        return state

    def measure(self, state: PipelineState) -> PipelineState:
        texts = {
            slice_id: [str(item.get("text") or "") for item in items]
            for slice_id, items in state.passages.items()
        }
        lenses = state.knowledge_extension.get("feature_lenses") or []
        metrics = compute_feature_metrics(texts, lenses)
        client = getattr(self.retriever, "client", None)
        analyze = getattr(client, "corpus_analysis_search", None)
        if callable(analyze):
            for slice_id, query in (state.search_queries or {}).items():
                local = metrics.setdefault(slice_id, {"passage_count": 0})
                slice_obj = None
                if state.intent:
                    slice_obj = next(
                        (item for item in state.intent.slices if item.slice_id == slice_id),
                        None,
                    )
                dataset_ids = dataset_ids_for_slice(slice_obj) if slice_obj else None
                try:
                    payload = analyze(query, dataset_ids=dataset_ids)
                    attach_corpus_analysis(local, payload)
                except RetrievalAPIError as exc:
                    attach_corpus_analysis(local, None, error=str(exc))
        state.feature_metrics = metrics
        state.status = "features_computed"
        return state

    def synthesize(self, state: PipelineState) -> PipelineState:
        intent = state.intent
        assert intent is not None
        citations: list[Citation] = []
        number = 1
        for slice_ in intent.slices:
            for index, item in enumerate(state.passages.get(slice_.slice_id) or []):
                dataset_id = str(item.get("dataset_id") or slice_.corpus_id or "")
                snippet = str(item.get("text") or "")
                citations.append(
                    Citation(
                        citation_id=f"ref_{number}",
                        slice_id=slice_.slice_id,
                        slice_label=slice_.label,
                        source_document=str(item.get("doc_id") or ""),
                        dataset_id=dataset_id,
                        corpus_name=corpus_name_for_id(dataset_id),
                        similarity=float(item["similarity"]) if item.get("similarity") is not None else None,
                        passage_index=index,
                        text_snippet=snippet[:_SNIPPET],
                    )
                )
                number += 1
        grouped: dict[str, list[RetrievedPassage]] = {
            slice_id: [RetrievedPassage.model_validate(item) for item in items]
            for slice_id, items in state.passages.items()
        }
        empty_labels = [
            slice_.label
            for slice_ in intent.slices
            if not (state.passages.get(slice_.slice_id) or [])
        ]
        answer = _synthesize_text(intent, grouped, citations)
        if getattr(dspy.settings, "lm", None) is not None and citations:
            try:
                prediction = dspy.Predict(GroundedSynthesizer)(
                    question=state.question,
                    evidence=_evidence_block(citations),
                )
                model_answer = str(getattr(prediction, "answer", "") or "").strip()
                if _answer_is_grounded(model_answer, citations, empty_labels):
                    answer = model_answer
            except Exception:
                pass
        citations = _mark_used(citations, answer)
        state.output = BenchmarkOutput(
            query_id=state.query_id,
            question=state.question,
            slices_evaluated=intent.slices,
            knowledge_extension=state.knowledge_extension,
            synthesized_answer=answer,
            feature_metrics=state.feature_metrics,
            grounded_citations=citations,
        )
        state.status = "ok"
        return state

    def run(self, question: str, query_id: str | None = None) -> PipelineState:
        state = self.resolve(question, query_id)
        if state.status == "clarification" or state.intent is None:
            return state
        state = self.extend(state)
        state = self.decompose(state)
        state = self.retrieve(state)
        state = self.measure(state)
        return self.synthesize(state)

    def forward(self, question: str, query_id: str | None = None) -> BenchmarkOutput:
        state = self.run(question, query_id)
        if state.output is None:
            raise ValueError(state.clarification or "The comparison did not proceed.")
        return state.output
