from __future__ import annotations

from dataclasses import dataclass

from app.core.policy import POLICY_VERSION, RULE_BY_CODE, risk_band
from app.rules.base import FileContext, FindingResult, Rule
from app.rules.common import FileSignatureRule, FileTypeRule
from app.rules.csv_rules import CsvDisclosureRule
from app.rules.document_rules import ImageMetadataRule, PdfRule, TextRule

SEVERITY_WEIGHT = {"LOW": 0.05, "MEDIUM": 0.25, "HIGH": 0.55, "CRITICAL": 1.0}
ACTION_PRIORITY = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}


@dataclass(frozen=True)
class CheckResult:
    decision: str
    risk_score: float
    risk_band: str
    policy_version: str
    findings: list[FindingResult]


def decision_from_findings(findings: list[FindingResult]) -> tuple[str, float]:
    actions: list[str] = []
    for item in findings:
        definition = RULE_BY_CODE.get(item.code)
        actions.append(definition.default_action if definition is not None else "REVIEW")
    decision = max(actions, key=lambda action: ACTION_PRIORITY[action], default="ALLOW")
    score = min(1.0, round(sum(SEVERITY_WEIGHT[item.severity] for item in findings), 3))
    return decision, score


class OutputChecker:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self.rules = rules or [
            FileTypeRule(),
            FileSignatureRule(),
            CsvDisclosureRule(),
            TextRule(),
            PdfRule(),
            ImageMetadataRule(),
        ]

    def check(self, context: FileContext) -> CheckResult:
        findings: list[FindingResult] = []
        for rule in self.rules:
            findings.extend(rule.evaluate(context))
        decision, score = decision_from_findings(findings)
        return CheckResult(
            decision=decision,
            risk_score=score,
            risk_band=risk_band(score),
            policy_version=POLICY_VERSION,
            findings=findings,
        )
