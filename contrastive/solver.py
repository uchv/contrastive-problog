from enum import Enum, auto
from typing import Sequence, Optional
from dataclasses import dataclass

from problog.ddnnf_formula import DDNNF

from engine import RuleParameter
from model import Intervention, Foil

class SolverStatus(Enum):
    SAT = auto()
    UNSAT = auto()
    UNKNOWN = auto()

@dataclass
class SolverResult:
    status: SolverStatus
    intervention: Optional[Intervention] = None

class Solver():
    def __init__(self, relevant_params: RuleParameter, circuit: DDNNF, foil: Sequence[Foil]):
        self.relevant_params: Sequence[RuleParameter] = relevant_params
        self.circuit: DDNNF = circuit
        self.foil: Sequence[Foil] = foil

    def solve_support(self, k: set[RuleParameter], exact=True):
        pass

