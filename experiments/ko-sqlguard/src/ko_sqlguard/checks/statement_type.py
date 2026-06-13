"""Statement-type gate: read-only allowlist, write permissions, and the
write-via-read vectors (data-modifying CTE, SELECT INTO, locking reads)."""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation
from ._ast import DDL_NODES, MUTATION_PERMIT, READ_NODE_TYPES, unwrap


def _permitted(node_type: type, policy: GuardPolicy) -> bool:
    flag = MUTATION_PERMIT.get(node_type)
    if flag is None:
        return False
    return bool(getattr(policy, flag, False))


def check_statement_type(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    violations: list[Violation] = []
    top = unwrap(stmt)

    # 1) Any mutating / command node ANYWHERE in the tree (catches DML hidden in
    #    CTEs and subqueries, plus the top statement itself). One violation per
    #    node type is enough to block.
    for node_type in MUTATION_PERMIT:
        if node_type is exp.Merge:
            continue  # MERGE is gated per-WHEN-action below (5).
        if stmt.find(node_type) is None or _permitted(node_type, policy):
            continue
        ddl = node_type in DDL_NODES
        violations.append(
            Violation(
                code="statement_type",
                severity=Severity.CRITICAL if ddl else Severity.HIGH,
                reason=(
                    f"{node_type.__name__.upper()} statement is not permitted "
                    f"under this policy (read_only={policy.read_only})"
                ),
                action="block",
                fix="Use a read-only SELECT, or enable the matching allow_* flag.",
            )
        )

    # 2) The top statement must itself be a read shape. Fail-closed against any
    #    node type not recognized above (future/unknown sqlglot nodes).
    if not isinstance(top, READ_NODE_TYPES) and not any(
        isinstance(top, t) for t in MUTATION_PERMIT
    ):
        violations.append(
            Violation(
                code="statement_type",
                severity=Severity.CRITICAL,
                reason=f"unsupported or non-read statement: {type(top).__name__}",
                action="block",
                fix="Only SELECT / set-operation reads are allowed.",
            )
        )

    # 3) SELECT ... INTO creates a table -> a write disguised as a read.
    for select in stmt.find_all(exp.Select):
        if select.args.get("into") is not None and not policy.allow_ddl:
            violations.append(
                Violation(
                    code="select_into",
                    severity=Severity.CRITICAL,
                    reason="SELECT ... INTO creates a table (write disguised as read)",
                    action="block",
                    fix="Remove INTO; SELECT results cannot be materialized to a new table.",
                )
            )

    # 4) Locking reads (FOR UPDATE / FOR SHARE) acquire row locks -> reject in
    #    read-only. Match the Lock node anywhere: a paren/subquery wrapper such as
    #    `(SELECT ...) FOR UPDATE` attaches the lock to the wrapper, not the inner
    #    Select, so scanning Select.locks alone misses it.
    if policy.read_only and stmt.find(exp.Lock) is not None:
        violations.append(
            Violation(
                code="locking_read",
                severity=Severity.HIGH,
                reason="FOR UPDATE / FOR SHARE acquires row locks; not a pure read",
                action="block",
                fix="Drop the FOR UPDATE/SHARE clause.",
            )
        )

    # 5) MERGE: gate each WHEN action by the matching allow_* flag. The DELETE
    #    action parses to Var('DELETE'), not exp.Delete, so a single allow_update
    #    gate (the old MUTATION_PERMIT mapping) let MERGE...THEN DELETE escalate.
    for when in stmt.find_all(exp.When):
        action = _merge_action(when.args.get("then"))
        if action is not None and not getattr(policy, f"allow_{action}", False):
            violations.append(
                Violation(
                    code="statement_type",
                    severity=Severity.HIGH,
                    reason=f"MERGE ... THEN {action.upper()} requires allow_{action} "
                    f"(read_only={policy.read_only})",
                    action="block",
                    fix=f"Enable allow_{action}, or remove the {action} action.",
                )
            )

    return violations


def _merge_action(then: exp.Expression | None) -> str | None:
    """The DML action of a MERGE WHEN clause: 'update' / 'insert' / 'delete'."""
    if isinstance(then, exp.Update):
        return "update"
    if isinstance(then, exp.Insert):
        return "insert"
    if isinstance(then, exp.Delete):
        return "delete"
    if isinstance(then, exp.Var) and (then.name or "").upper() == "DELETE":
        return "delete"
    return None
