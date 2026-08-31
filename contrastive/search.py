from itertools import combinations
from typing import Sequence


from engine import Engine
from solver import SolverStatus
from model import Explanation, RuleParameter


def _get_support_candidates(cardinality: int, relevant: Sequence[RuleParameter], min_supps: set[tuple[RuleParameter]], infeasible: set[tuple[RuleParameter]]) -> Sequence:
    result = []
    for candidate in combinations(relevant, cardinality):
        # superset of minimally feasible support cannot be minimal
        if any(s <= frozenset(candidate) for s in min_supps):
            continue

        # subset of infeasible support cannot be feasible
        if any(s >= frozenset(candidate) for s in infeasible):
            continue

        result.append(candidate)
    # print(f"Candidates for support with cardinality {cardinality}: {[str([r.original_rule for r in c]) for c in result]}")
    return result


upper_bound_checked = set()
def enumerate_explanations(engine: Engine) -> Sequence[Explanation]:
    relevant = engine.get_relevant_parameters()

    # min_supps and infeasible are used to skip supports which cannot be minimally feasible
    min_supps = set() 
    infeasible = set()

    interventions = []

    supports_checked = 0    # only for debug info
    for i in range(1, len(relevant)+1):
        supps_found = set()

        # check all subsets of size i
        for k in _get_support_candidates(i, relevant, min_supps, infeasible):
            result = engine.find_intervention_for_support(k, exact=True)
            supports_checked += 1
            
            if result.status == SolverStatus.SAT:
                supps_found.add(frozenset(k))
                interventions.append(result.intervention)
                # print(f"SAT: {[str(param.original_rule) for param in k]}")
            elif result.status == SolverStatus.UNKNOWN:
                print(f"WARNING: Solver could not solve feasiblity problem for support { k }")
        
        # now check the maximally big supports minus already found supports
        j = len(relevant) - i + 1
        if i >= j:
            continue # no pruning at this level
        # we purposely pass the min_supps set without the newly found supports, as we subtract those later
        for k in _get_support_candidates(j, relevant, min_supps, infeasible):
            k = frozenset(k)
            for s in supps_found:
                k = k - s if s <= k else k
            # print(f"Checking { str([p.original_rule for p in k]) }")
            supports_checked += 1
            result = engine.find_intervention_for_support(k, exact=False)
            if result.status == SolverStatus.UNSAT:
                infeasible.add(frozenset(k))
                # print("Infeasible found: " + str([p.original_rule for p in k]))
            elif result.status == SolverStatus.UNKNOWN:
                print(f"WARNING: Solver could not solve feasiblity problem for support { k }")

        min_supps = min_supps.union(supps_found)

    # DEBUG INFO    
    print(f"Checked feasibility for {supports_checked} supports.")


    return [Explanation(interv) for interv in interventions]
            