"""Problem and offering-fit analysis with strict evidence validation.

Two analyzers are provided:

* :class:`RuleBasedAnalyzer` is deterministic and only cites retrieved sources.
  It produces a modest-confidence interpretation and clearly labels missing
  evidence.
* :class:`LLMAnalyzer` wraps an AI provider but rejects any output that cites a
  URL that was not actually retrieved for the company, or that cites nothing at
  all. On rejection the orchestrator falls back to the rule-based analyzer.

Neither analyzer is allowed to state that an unverified fact is verified.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.engine.contracts import (
    CompanyCandidate,
    CompanyResearch,
    ICPQuery,
    ProblemFitAnalysis,
)
from app.engine.errors import EvidenceValidationError
from app.engine.evidence import sanitize_sources, validate_references

SYSTEM_PROMPT = (
    "You analyse B2B prospecting research. Use ONLY the supplied research and "
    "sources. Cite only URLs present in the supplied sources. Clearly separate "
    "observed facts from your interpretation. Never invent a problem, number, "
    "person, email or source. If the evidence is insufficient, say so explicitly "
    "and use a low confidence value."
)


class ProblemFitAnalyzer(ABC):
    """Turns research into a specific problem and a fit explanation."""

    name: str = "rule_based"
    synthetic: bool = False

    @abstractmethod
    def analyze(
        self,
        *,
        company: CompanyCandidate,
        research: CompanyResearch,
        icp: ICPQuery,
        client_context: dict[str, Any],
    ) -> ProblemFitAnalysis:
        """Return a validated analysis for the company."""
        raise NotImplementedError


class RuleBasedAnalyzer(ProblemFitAnalyzer):
    """Deterministic analyzer that only restates retrieved signals."""

    name = "rule_based"

    def analyze(
        self,
        *,
        company: CompanyCandidate,
        research: CompanyResearch,
        icp: ICPQuery,
        client_context: dict[str, Any],
    ) -> ProblemFitAnalysis:
        """Build a problem and fit statement from observed signals."""
        sources = sanitize_sources(research.evidence)
        urls = [source.url for source in sources]
        signals = [signal.strip() for signal in research.observable_signals if signal.strip()]
        offering = (
            client_context.get("products_services")
            or client_context.get("value_proposition")
            or client_context.get("problems_solved")
            or ""
        )
        offering_reference = offering.strip()[:400] or None
        synthetic = research.synthetic
        missing: list[str] = list(research.missing_information)
        if not urls:
            missing.append("no retrievable sources were collected for this company")
        if not offering:
            missing.append("client offering is not configured on the business profile")

        if signals:
            problem = (
                "Observed signals indicate friction around: "
                + "; ".join(signals[:3])
            )
            problem_confidence = min(0.5, 0.15 + 0.1 * len(signals) + 0.05 * len(urls))
        else:
            problem = (
                "No specific business problem can be evidenced from the retrieved "
                "sources for this company."
            )
            problem_confidence = 0.05
            missing.append("a specific, evidenced business problem")

        inference = (
            f"Rule-based inference from {len(signals)} observed signal(s) and "
            f"{len(urls)} retrieved source(s). This is an interpretation of the "
            "retrieved material, not a verified fact."
        )
        if synthetic:
            problem = f"[Synthetic demo only] {problem}"
            inference = (
                "Synthetic demo record: no real company, person or source exists. "
                "This analysis is illustrative only."
            )
            problem_confidence = min(problem_confidence, 0.15)

        if offering_reference and signals:
            fit_explanation = (
                f"The client offers '{offering_reference}'. If the observed signals hold, "
                "that offering addresses the stated problem for this company. The fit is "
                "a hypothesis until a human reviews the cited sources."
            )
            fit_confidence = min(0.45, problem_confidence + 0.05)
        else:
            fit_explanation = (
                "A credible fit cannot be stated yet: "
                + ("no offering is configured. " if not offering_reference else "")
                + "the research does not contain enough evidence to link the offering "
                "to a specific problem."
            )
            fit_confidence = 0.0

        return ProblemFitAnalysis(
            problem=problem,
            problem_inference=inference,
            problem_confidence=round(problem_confidence, 3),
            fit_explanation=fit_explanation,
            offering_reference=offering_reference,
            fit_confidence=round(fit_confidence, 3),
            evidence_urls=urls,
            missing_information=_unique(missing),
            analyzer=self.name,
            synthetic=synthetic,
            validation_notes=(
                ["analysis is based on synthetic demo records"] if synthetic else []
            ),
        )


class LLMAnalyzer(ProblemFitAnalyzer):
    """LLM-backed analyzer whose citations must match retrieved sources."""

    name = "llm"

    def __init__(self, provider: Any) -> None:
        """Wrap an ``AIAnalysisProvider`` implementation."""
        self._provider = provider

    def analyze(
        self,
        *,
        company: CompanyCandidate,
        research: CompanyResearch,
        icp: ICPQuery,
        client_context: dict[str, Any],
    ) -> ProblemFitAnalysis:
        """Call the LLM and reject unsourced or uncited output."""
        sources = sanitize_sources(research.evidence)
        if not sources:
            raise EvidenceValidationError(
                "no retrieved sources are available, so an LLM analysis cannot be grounded"
            )
        prompt = _build_prompt(
            company=company,
            research=research,
            icp=icp,
            client_context=client_context,
            source_urls=[source.url for source in sources],
        )
        try:
            raw = self._provider.analyze(prompt, ProblemFitAnalysis, system=SYSTEM_PROMPT)
            analysis = (
                raw
                if isinstance(raw, ProblemFitAnalysis)
                else ProblemFitAnalysis.model_validate(raw)
            )
        except EvidenceValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize provider/model failures
            raise EvidenceValidationError(
                f"LLM analysis could not be validated: {exc}"
            ) from exc
        cited, unsupported = validate_references(analysis.evidence_urls, sources)
        if unsupported:
            raise EvidenceValidationError(
                "analysis cited sources that were not retrieved: "
                + ", ".join(unsupported[:3])
            )
        if not cited:
            raise EvidenceValidationError(
                "analysis cited no retrieved sources; refusing to accept it"
            )
        return analysis.model_copy(
            update={"analyzer": self.name, "synthetic": False}
        )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _build_prompt(
    *,
    company: CompanyCandidate,
    research: CompanyResearch,
    icp: ICPQuery,
    client_context: dict[str, Any],
    source_urls: list[str],
) -> str:
    """Build a grounded analysis prompt for the LLM provider."""
    evidence_lines = "\n".join(
        f"- {source.url} :: {source.title or ''} :: {(source.snippet or '')[:300]}"
        for source in research.evidence
        if source.url in source_urls
    )
    return (
        "COMPANY\n"
        f"name: {company.name}\n"
        f"website: {company.website or company.domain}\n"
        f"industry: {company.industry}\n"
        f"location: {company.location}\n\n"
        "RESEARCH\n"
        f"what_it_does: {research.what_it_does}\n"
        f"what_it_sells: {research.what_it_sells}\n"
        f"who_it_serves: {research.who_it_serves}\n"
        f"positioning: {research.positioning}\n"
        f"observed_signals: {research.observable_signals}\n\n"
        "CLIENT OFFERING\n"
        f"products_services: {client_context.get('products_services')}\n"
        f"value_proposition: {client_context.get('value_proposition')}\n"
        f"problems_solved: {client_context.get('problems_solved')}\n"
        f"target_audience: {client_context.get('target_audience')}\n\n"
        "ICP\n"
        f"industries: {icp.industries}\n"
        f"countries: {icp.countries}\n"
        f"company_size: {icp.company_size}\n\n"
        "SOURCES (cite only these exact URLs in evidence_urls)\n"
        f"{evidence_lines or '(none)'}\n\n"
        "Return a specific business problem supported by the sources, an explicit "
        "problem_inference explaining how you reached it, and a fit explanation "
        "that references the client offering. Use evidence_urls only from SOURCES."
    )
