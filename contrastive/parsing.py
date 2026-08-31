from typing import Tuple

from model import CEP, Foil, Frame, RuleKind, ContrastiveProgram
from problog.program import PrologString
from problog.logic import Term

_MARKER_FUNCTOR = "ce_mark"
_MARKER_KINDS = {
    "s": RuleKind.SAFE,
    "safe": RuleKind.SAFE,
    "a": RuleKind.ASSUMABLE,
    "assumable": RuleKind.ASSUMABLE,
    "d": RuleKind.DELETABLE,
    "deletable": RuleKind.DELETABLE,
}

_FOIL_FUNCTOR = "foil"


def _get_kind_from_marker(mark: str) -> RuleKind:
    return _MARKER_KINDS[mark.lower()]


def _attempt_parse_marker(rule: Term) -> RuleKind:
    """
    Takes rule, returns the respective RuleKind if it is a valid rule annotation, or None if it is not.
    """
    if type(rule) is not Term:
        return
    if rule.functor != _MARKER_FUNCTOR:
        return None

    if rule.arity != 1:
        raise ValueError(
            f"{ _MARKER_FUNCTOR } expects exactly 1 argument."
        )
    if hasattr(rule, "head") and rule.head.probability is not None:
        raise ValueError(
            f"{ _MARKER_FUNCTOR } should not have a probability."
        )

    # we allow both " and ' quotes
    arg = str(rule.args[0]).strip("'\"")

    return _get_kind_from_marker(arg)


# TODO: DEBUG
def _attempt_parse_foil(rule: Term) -> Tuple[Foil]:
    """
    Takes rule, returns a foil if it is a foil annotation, or None if it is not.
    """
    if type(rule) is not Term:
        return
    if rule.functor != _FOIL_FUNCTOR:
        return None

    if rule.arity != 3:
        raise ValueError(
            f"{ _FOIL_FUNCTOR } expects exactly 3 arguments."
        )
    if hasattr(rule, "head") and rule.head.probability is not None:
        raise ValueError(
            f"{ _FOIL_FUNCTOR } should not have a probability."
        )

    query = rule.args[0]  # should be Term type
    lo, hi = [float(str(a).strip()) for a in rule.args[1:]]

    if lo < 0 or lo > 1 or hi < 0 or hi > 1:
        raise ValueError("Foil intervals should be between 0 and 1.")

    return Foil(query, lo, hi)


def parse_annotated(text: str) -> CEP:
    # let problog parse program text, then go through each rule to filter annotations
    program = PrologString(text)
    result = ContrastiveProgram()
    foils = []

    latest_marker = None
    for rule in program:
        # check if the current rule is an annotation
        marker = _attempt_parse_marker(rule)
        # check if the current rule is a foil
        foil = _attempt_parse_foil(rule)

        if marker is not None:
            if latest_marker is not None:
                raise ValueError(
                    f"Only one { _MARKER_FUNCTOR } per rule allowed."
                )

            latest_marker = marker
        elif foil is not None:
            foils.append(foil)
        else:
            kind = latest_marker or RuleKind.FREE
            if (
                (
                    kind == RuleKind.ASSUMABLE
                    or kind == RuleKind.DELETABLE
                )
                and hasattr(rule, "head")
                and rule.head.probability is not None
            ):
                raise ValueError(
                    "Assumable/Deletable rules should not have probabilities."
                )
            result.add_rule(rule, kind)

            # consume latest marker
            latest_marker = None

    return CEP(Frame(result), [f.query for f in foils], foils)
