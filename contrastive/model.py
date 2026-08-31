from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Sequence, Tuple
from problog.program import SimpleProgram
from problog.logic import Term 


class RuleKind(Enum):
    FREE = auto()
    SAFE = auto()
    ASSUMABLE = auto()
    DELETABLE = auto()


@dataclass
class Foil:
    query: Term
    lower: float
    upper: float

@dataclass
class AnnotatedRule:
    rule: Term # Term is the problog2 super class of Clause, AnnotatedDisjunction, etc.
    kind: RuleKind

@dataclass(eq=False) # make it hashable so it can appear in set
class RuleParameter:
    kind: RuleKind
    original_rule: Term
    probability: float
    functor: str
    circuit_nodes: list[int] # corresponding nodes in compiled circuit (id)

class ContrastiveProgram(SimpleProgram):
    def __init__(self):
        super().__init__()

        # each rule in self has an index-corresponding entry in self.rule_kinds.
        self.rule_kinds = []

    def add_rule(self, rule: Term, kind: RuleKind):
        self.add_statement(rule)
        self.rule_kinds.append(kind)

    def get_annotated_rules(self) -> Sequence[Tuple[RuleKind, Term]]:
        return [(self.rule_kinds[i], list(self)[i]) for i in range(len(self.rule_kinds))]

    @property
    def safe_rules(self) -> Sequence[Term]:
        self._get_rules_by_kind(RuleKind.SAFE)

    @property
    def assumable_rules(self) -> Sequence[Term]:
        self._get_rules_by_kind(RuleKind.ASSUMABLE)

    @property
    def deletable_rules(self) -> Sequence[Term]:
        self._get_rules_by_kind(RuleKind.DELETABLE)

    def _get_rules_by_kind(self, kind: RuleKind) -> Sequence[Tuple]:
        return [list(self)[i] for i in range(len(self.rule_kinds)) if self.rule_kinds[i] == kind]
    


@dataclass
class Frame:
    program: ContrastiveProgram  # valid ProbLog program WITHOUT annotations/foil

    @property
    def safe_rules() -> Sequence[Term]:
        pass

    @property   
    def assumable_rules() -> Sequence[Term]:
        pass

    @property
    def deletable_rules() -> Sequence[Term]:
        pass


@dataclass
class CEP:
    frame: Frame
    queries: Sequence[Term]
    foil: Sequence[Foil]   # one closed interval per query

@dataclass
class Intervention:
    values: dict[RuleParameter, float]
    delta: dict[RuleParameter, float]
    query_probabilities: dict[Term, float]

@dataclass
class Explanation:
    intervention: Intervention

    def __str__(self) -> str:
        lines = []

        if self.intervention.query_probabilities:
            for query, probability in self.intervention.query_probabilities.items():
                lines.append(f"P({query}) = {probability:.4f}")
            lines.append("")

        for param, delta in sorted(self.intervention.delta.items(), key=lambda item: str(item[0].original_rule)):
            old = float(param.probability)
            new = old + delta
            if param.kind == RuleKind.ASSUMABLE:
                lines.append(f"- add    {param.original_rule}")
            elif param.kind == RuleKind.DELETABLE:
                lines.append(f"- remove {param.original_rule}")
            else:
                lines.append(f"- {param.original_rule}: {old:.4f} -> {new:.4f} ({delta:+.4f})")

        if not lines:
            lines.append("(empty intervention)")

        return "\n".join(lines)

class InvalidFoil(Exception):
    pass