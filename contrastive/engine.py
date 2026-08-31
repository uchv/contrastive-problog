import itertools
from typing import Optional, Sequence
import re

from problog.program import SimpleProgram, LogicProgram
from problog.logic import Term, Clause, And, AnnotatedDisjunction, Constant
from problog.formula import LogicFormula, LogicDAG, BaseFormula
from problog.cnf_formula import CNF
from problog.ddnnf_formula import DDNNF
from model import CEP, RuleKind, RuleParameter
from solver import SolverResult
from solverz3 import SolverZ3

_ASSUMABLE_FUNCTOR_PREFIX = "ce_assum_"
_DELETABLE_FUNCTOR_PREFIX = "ce_delet_"
_PARAMETER_FUNCTOR_PREFIX = "ce_param_"
_PLACEHOLDER_PROB = 0.5

class Engine:
    def __init__(self, cep: CEP):
        self.cep = cep
        self.frame = cep.frame

        self.id_generator = itertools.count(1)
        self.params: list[RuleParameter] = []
        # maps circuit node id -> Parameter
        self.params_term_map: dict[int, list[RuleParameter]] = {}

        self.circuit: DDNNF = None
        self.program: LogicProgram = None
        
        self._transform_program()
        self._compute_circuit()

        self.relevant_params = self.get_relevant_parameters()
        self.solver = SolverZ3(self.relevant_params, self.circuit, self.cep.foil)

    def _get_head_and_body(self, rule: Term) -> tuple[Term, Optional[Term]]:
        if isinstance(rule, Clause):
            return rule.head, rule.body

        if isinstance(rule, AnnotatedDisjunction):
            raise ValueError("Annotated disjunctions are not allowed.")

        return rule, None


    def _transform_rule(self, r: Term, k: RuleKind) -> Sequence[Term]:
        if k != RuleKind.ASSUMABLE and k != RuleKind.DELETABLE and k != RuleKind.FREE:
            raise NotImplementedError("This function only transforms assumable/deletables")

        functor_name = {
            RuleKind.ASSUMABLE: _ASSUMABLE_FUNCTOR_PREFIX,
            RuleKind.DELETABLE: _DELETABLE_FUNCTOR_PREFIX,
            RuleKind.FREE: _PARAMETER_FUNCTOR_PREFIX
        }

        result = []

        # Add a probabilistic fact for the rule to ensure it ends up in circuit
        functor = f"{ functor_name[k] }{ next(self.id_generator) }"
        fact = Term(functor, *tuple(r.variables())) # * unpacks tuple
        result.append(fact.with_probability(Constant(_PLACEHOLDER_PROB)))

        # append fact to body of rule
        head, body = self._get_head_and_body(r)
        if body is None:
            guarded_body = fact
        else:
            guarded_body = And(body, fact)
        guarded_rule = Clause(head.with_probability(None), guarded_body)
        result.append(guarded_rule)  

        # keep track of resulting parameter 
        if k == RuleKind.ASSUMABLE:
            real_prob = 0.0
        elif k == RuleKind.DELETABLE:
            real_prob = 1.0
        else: # k == RuleKind.FREE
            probability = head.probability
            if probability is None:
                real_prob = 1.0
            else:
                real_prob = float(probability.compute_value())
        self.params.append(RuleParameter(k, r, real_prob, functor, []))

        return result  

    def _transform_program(self) -> LogicProgram:
        result = SimpleProgram()
        

        for (k, r) in self.frame.program.get_annotated_rules():
            if k == RuleKind.SAFE:
                result.add_statement(r)
            else:
                for m in self._transform_rule(r, k):
                    result.add_statement(m)

        self.program = result

    def _collect_switch_facts(self) -> None:
        rule_names = [(str(name), node_id) for (name, node_id) in self.circuit.get_names(BaseFormula.LABEL_NAMED)]
        for param in self.params:
            # for ground facts, problog names the corresponding items with the given functor.
            # for non-ground facts, a set of facts choice(id, 0, functor(instance), instance) is created
            # regex finds all strings where functor is present ((?!\d) rejects a match if another digit follows -> 
            # e.g. ce_delet11 does not match when looking for ce_delet1)
            circuit_ids = [nid for (name, nid) in rule_names if re.search(param.functor+"(?!\d)", name)] 
            param.circuit_nodes = circuit_ids
            for cid in circuit_ids:
                self.params_term_map[cid] = param            

    def _compute_circuit(self) -> None:
        queries = self.cep.queries
        if not queries:
            raise ValueError("Need at least 1 Foil")

        grounded = LogicFormula.create_from(self.program, queries=queries, evidence=[], label_all=True, avoid_name_clash=True)
        dag = LogicDAG.create_from(grounded)
        cnf = CNF.create_from(dag)
        self.circuit = DDNNF.create_from(cnf, smooth=True)
        self._collect_switch_facts()                

    def evaluate_success_probabilities(self) -> dict[Term, float]:
        weights = {node: p.probability for p in self.params for node in p.circuit_nodes}
        probs = self.circuit.evaluate(weights=weights)

        return { query: prob for query, prob in probs.items() }

    def get_relevant_parameters(self) -> list[RuleParameter]:
        if self.circuit is None:
            raise ValueError("No compiled circuit available.")

        return set([self.params_term_map[id] 
                    for name, id in self.circuit.get_names(BaseFormula.LABEL_NAMED) 
                    if id in self.params_term_map])

    def find_intervention_for_support(self, k: set[RuleParameter], exact=True) -> SolverResult:
        # we create a symbolic variable for each parameter in the support
        # Note that the support cannot include safe rules
        # We do not need symbolic variables for rules outside the set of 
        # relevant rules, as they can be converted to constants immediately
        # variables = { p :  for p in k }
        return self.solver.solve_support(k, exact=exact)