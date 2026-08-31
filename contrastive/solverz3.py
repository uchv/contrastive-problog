from typing import Any, Sequence, Collection
from z3 import SolverFor, Real, RealVal, Or, ArithRef, AlgebraicNumRef, simplify, is_rational_value, ModelRef, sat, unsat, unknown

from solver import Solver, SolverResult, SolverStatus
from engine import RuleParameter
from model import RuleKind, Foil, Intervention
from problog.evaluator import Semiring, OperationNotSupported
from problog.ddnnf_formula import DDNNF
from problog.logic import Term

class SemiringZ3(Semiring):
    def __init__(self, symbols: dict[str, ArithRef]) -> None:
        self.symbols = symbols

    def one(self) -> ArithRef:
        return RealVal(1)

    def zero(self) -> ArithRef:
        return RealVal(0)

    def is_one(self, value: Any) -> bool:
        simplified = simplify(value)

        return is_rational_value(simplified) and simplified.numerator_as_long() == simplified.denominator_as_long()

    def is_zero(self, value: Any) -> bool:
        simplified = simplify(value)
        return is_rational_value(simplified) and simplified.numerator_as_long() == 0

    def plus(self, left: ArithRef, right: ArithRef) -> ArithRef:
        return left + right

    def times(self, left: ArithRef, right: ArithRef) -> ArithRef:
        return left * right

    def negate(self, value: ArithRef) -> ArithRef:
        return self.one() - value

    def value(self, value: Any) -> ArithRef:
        if isinstance(value, ArithRef):
            return value

        if isinstance(value, str) and value in self.symbols:
            return self.symbols[value]

        # ProbLog Constant
        if hasattr(value, "compute_value"):
            value = value.compute_value()

        if isinstance(value, bool):
            return RealVal(1 if value else 0)

        return RealVal(str(value))

    def result(self, value: ArithRef, formula=None) -> ArithRef:
        return value

    def normalize(self, value: ArithRef, normalization: ArithRef) -> ArithRef:
        raise OperationNotSupported()

    def is_dsp(self) -> bool:
        return True



class SolverZ3(Solver):
    def __init__(
        self,
        relevant_params: Sequence[RuleParameter],
        circuit: DDNNF,
        foil: Sequence[Foil]
    ) -> None:
        super().__init__(relevant_params=relevant_params, circuit=circuit, foil=foil)

        # quantifier free, non-linear real arithmetic solver
        self.solver = SolverFor("QF_NRA")

        self.timeout_ms = None
        self.validation_tolerance = 1e-7

        self._parameter_index = {param: idx for idx, param in enumerate(self.relevant_params)}

        self._base_constraints = []
        self._create_base_constraints()
        
    @staticmethod
    def _real(value: Any) -> ArithRef:
        if hasattr(value, "compute_value"):
            value = value.compute_value()
        return RealVal(str(value))

    @staticmethod
    def _number_to_float(value: ArithRef) -> float:
        value = simplify(value)

        if is_rational_value(value):
            return value.numerator_as_long() / value.denominator_as_long()

        if isinstance(value, AlgebraicNumRef):
            approximation = value.approx(10)    # TODO: parameterize precision

            return approximation.numerator_as_long() / approximation.denominator_as_long()

        raise TypeError("Could not parse {value}.")

    def _create_parameter_variables(self, solver: Solver) -> dict[RuleParameter, ArithRef]:
        variables: dict[RuleParameter, ArithRef] = {}

        for parameter in self.relevant_params:
            index = self._parameter_index[parameter]
            variable = Real(f"x_{index}")

            variables[parameter] = variable

            if parameter.kind == RuleKind.ASSUMABLE:
                # if an assumable rule is in a support, we know that its value 
                # must be switched 
                self._base_constraints.append(Or(variable == self._real(0), variable == self._real(1)))
            elif parameter.kind == RuleKind.DELETABLE:
                # similar for deletable rules
                self._base_constraints.append(Or(variable == self._real(0), variable == self._real(1)))
            else:
                # CONSTRAINT 0 <= x <= 1
                self._base_constraints.extend([self._real(0) <= variable, variable <= self._real(1)])

        return variables

    def _create_circuit_weights(self, parameter_variables: dict[RuleParameter,ArithRef]
    ) -> tuple[dict[int, str], dict[str, ArithRef]]:
        weights: dict[int, str] = {}
        symbols: dict[str, ArithRef] = {}

        for parameter in self.relevant_params:
            variable = parameter_variables.get(parameter)

            if variable is None:
                weight_symbol = str(parameter.probability)
            else:
                index = self._parameter_index[parameter]
                weight_symbol = f"__ce_z3_parameter_{index}"
                symbols[weight_symbol] = variable

            for circuit_node_id in parameter.circuit_nodes:
                weights[circuit_node_id] = weight_symbol


        return weights, symbols

    def _derive_query_expressions(self, parameter_variables: dict[RuleParameter, ArithRef]
    ) -> dict[Term, ArithRef]:
        weights, symbols = self._create_circuit_weights(parameter_variables)
        # print("Weights: " + str(weights))
        # print("Symbols: " + str(symbols))

        semiring = SemiringZ3(symbols)
        evaluated = self.circuit.evaluate(semiring=semiring, weights=weights)
        # print("evaluated: " + str(evaluated))

        result: dict[Term, ArithRef] = {}

        for constraint in self.foil:
            # print(evaluated[constraint.query])
            result[constraint.query] = simplify(evaluated[constraint.query])

        return result

    def _create_base_constraints(self) -> None:
        self._parameter_variables = self._create_parameter_variables(self.solver)
        self._query_expressions = self._derive_query_expressions(self._parameter_variables)
        for constraint in self.foil:
            expression = self._query_expressions[constraint.query]
            self._base_constraints.extend([self._real(constraint.lower) <= expression, expression <= self._real(constraint.upper)])
        self.solver.add(*self._base_constraints) 

    def _get_support_constraints(self, k: Sequence[RuleParameter], exact: bool = True) -> Sequence:
        result = []
        for param, var in self._parameter_variables.items():
            if param not in k:
                result.append(var == self._real(param.probability))
            elif exact and param.kind == RuleKind.ASSUMABLE:
                result.append(var == self._real(1))
            elif exact and param.kind == RuleKind.DELETABLE:
                result.append(var == self._real(0))
        return result

    def _extract_intervention(self, model: ModelRef, parameter_variables: dict[RuleParameter, ArithRef], query_expressions: dict[Term, ArithRef]
    ) -> Intervention:
        values: dict[Term, float] = {}

        for parameter in self.relevant_params:
            variable = parameter_variables.get(parameter)

            if variable is None:
                value = float(parameter.probability)
            else:
                interpretation = model.get_interp(variable.decl())
                if interpretation is not None:
                    value = self._number_to_float(interpretation)

            values[parameter] = value
            
        delta = {
            param: value - float(param.probability)
            for param, value in values.items()
            if abs(value - float(param.probability)) > self.validation_tolerance
        }

        query_probabilities = {
            query: self._number_to_float(model.eval(expression, model_completion=True))
            for query, expression in query_expressions.items()
        }

        return Intervention(values=values, delta=delta, query_probabilities=query_probabilities)

        # self._validate_intervention(intervention)
        # return intervention

    # TODO: For A and D, we can set values exactly. For 1-supports, we can even
    # skip math opt and evaluate queries directly.
    def solve_support(self, support: Collection[RuleParameter], exact: bool = True) -> SolverResult:
        """
        This method finds an arbitrary feasible intervention, no guarantee of magnitude minimality).
        """
        support = set(support)

        if len(support - set(self.relevant_params)) > 0:
            raise ValueError("Support contains illegal elements.")

        # TODO: If we do not need timeout, then remove this from code
        if self.timeout_ms is not None:
            self.solver.set(timeout=self.timeout_ms)

        try:
            # base constraints were already inserted in _create_base_constraints
            # now we just update the support variables
            self.solver.push()
            self.solver.add(*self._get_support_constraints(k=support, exact=exact))

            status = self.solver.check()

            # except Exception as error:
            #     print(f"Exception: {error}")
            #     return SolverResult(SolverStatus.UNKNOWN)

            if status == unsat:
                return SolverResult(SolverStatus.UNSAT)

            if status == unknown:
                print(f"Unknown: {self.solver.reason_unknown()}")
                return SolverResult(SolverStatus.UNKNOWN)

            model = self.solver.model()

            intervention = self._extract_intervention(model, self._parameter_variables, self._query_expressions)

            return SolverResult(SolverStatus.SAT, intervention)
        finally: 
            self.solver.pop()