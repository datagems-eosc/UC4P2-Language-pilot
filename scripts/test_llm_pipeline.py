#!/usr/bin/env python3
"""Test the question-understanding pipeline via Scayle LLM.

Runs four stages locally — no Break model, no external API:
  1. route        – extract the concept being compared
  2. disambiguate – parse periods, languages, slices
  3. extend       – LLM-powered facet / lemma / lens expansion
  4. decompose    – LLM-only sub-question decomposition (DSPy backend)

Usage
-----
    PYTHONPATH=. python scripts/test_llm_pipeline.py
    PYTHONPATH=. python scripts/test_llm_pipeline.py --provider ollama
    PYTHONPATH=. python scripts/test_llm_pipeline.py --question "How was love described in 1850 vs 1950?"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.decomposition.base import QDMRStep
from src.decomposition.factory import QDMRDecomposerFactory
from src.knowledge_extension.expander import expand_knowledge, knowledge_extension_payload
from src.llm import configure_refinement_lm, llm_endpoint, selected_model
from src.routing.router import route_query
from src.schemas.slice import ComparisonSlice, ParsedQueryIntent, parse_query_intent


BENCHMARK_QUESTIONS = [
    "How did descriptions of Dresden differ in English sources from 1800 and 1900?",
    "How was marriage described in German texts from the 1850s versus English texts from the 1850s?",
    "How was love portrayed in 1820 compared to 1920?",
]

SEPARATOR = "─" * 72


def banner(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def step_header(number: int, name: str) -> None:
    print(f"\n  ┌── Step {number}: {name}")


def step_done(elapsed: float) -> None:
    print(f"  └── done in {elapsed:.1f}s")


def show_route(question: str) -> str:
    step_header(1, "Route (concept extraction)")
    t0 = time.time()
    decision = route_query(question)
    step_done(time.time() - t0)
    print(f"      domain  : {decision.domain}")
    print(f"      concept : {decision.concept or '(none)'}")
    return decision.concept or ""


def show_disambiguate(question: str, llm_concept: str = "") -> ParsedQueryIntent | None:
    step_header(2, "Disambiguate (local parse + LLM fallback)")
    t0 = time.time()
    intent, errors = parse_query_intent(question)
    step_done(time.time() - t0)

    if intent is None and errors:
        concept_missing = any("concept" in e.lower() for e in errors)
        slice_missing = any("slice" in e.lower() or "comparison" in e.lower() for e in errors)
        if concept_missing and not slice_missing and llm_concept:
            print(f"      ↳ regex missed concept, using LLM-extracted: {llm_concept}")
            patched_query = f"How were descriptions of {llm_concept} different {question.split('in ', 1)[-1] if ' in ' in question else question}"
            intent, errors = parse_query_intent(patched_query)
            if intent:
                intent.original_query = question
                intent.target_concept = llm_concept

    if errors:
        for err in errors:
            print(f"      ⚠ {err}")
    if intent is None:
        return None
    print(f"      concept   : {intent.target_concept}")
    print(f"      dimension : {intent.dimension}")
    print(f"      slices    : {len(intent.slices)}")
    for s in intent.slices:
        print(f"        {s.slice_id}: {s.label}  ({s.period_start}–{s.period_end}, {s.language})")
    return intent


def show_extend(question: str, concept: str, slices: list[ComparisonSlice]) -> dict:
    step_header(3, "Extend knowledge (LLM)")
    t0 = time.time()
    expansion = expand_knowledge(question, concept, slices)
    step_done(time.time() - t0)
    payload = knowledge_extension_payload(expansion)
    print(f"      facets : {payload.get('thematic_facets', [])}")
    print(f"      lenses : {payload.get('feature_lenses', [])}")
    for s in slices:
        variants = payload.get(s.slice_id, [])
        if variants:
            print(f"      {s.slice_id} lemmas: {variants}")
    return payload


def show_decompose(
    question: str,
    slices: list[ComparisonSlice],
    concept: str,
) -> list[QDMRStep]:
    step_header(4, "Decompose (LLM only, no Break)")
    decomposer = QDMRDecomposerFactory.create(backend="dspy")
    t0 = time.time()
    steps = decomposer.decompose(question, slices, concept)
    step_done(time.time() - t0)
    used_fallback = getattr(decomposer, "used_fallback", None)
    if used_fallback:
        print(f"      ⚠ fallback used: {getattr(decomposer, 'last_error', '')}")
    for st in steps:
        refs = f"  → refs {st.references}" if st.references else ""
        print(f"      {st.instruction}{refs}")
    return steps


def run_one(question: str) -> None:
    banner(question)

    concept = show_route(question)
    intent = show_disambiguate(question, llm_concept=concept)
    if intent is None:
        print("\n  ✗ Question could not be disambiguated — skipping remaining steps.")
        return

    concept = intent.target_concept or concept or "the subject"
    expansion = show_extend(question, concept, intent.slices)
    steps = show_decompose(question, intent.slices, concept)

    print(f"\n  ✓ Pipeline completed: {len(steps)} sub-questions produced")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM pipeline smoke-test")
    parser.add_argument("--provider", default="scayle", help="LLM provider (scayle, ollama, openai)")
    parser.add_argument("--question", default=None, help="Single question instead of benchmarks")
    args = parser.parse_args()

    label = configure_refinement_lm(prefer=args.provider, force=True)
    if not label:
        print(f"✗ Could not configure LLM provider '{args.provider}'")
        sys.exit(1)
    print(f"LLM : {label}")
    print(f"URL : {llm_endpoint()}")

    os.environ["QDMR_BACKEND"] = "dspy"

    questions = [args.question] if args.question else BENCHMARK_QUESTIONS
    for q in questions:
        run_one(q)

    print(f"\n{'═' * 72}")
    print(f"  All {len(questions)} question(s) processed.")
    print(f"{'═' * 72}")


if __name__ == "__main__":
    main()
