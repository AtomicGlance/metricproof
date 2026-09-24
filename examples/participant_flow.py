"""Synthetic participant flow; no real people or clinical conclusions."""

from metricproof import (
    check_grouped_reconciliation,
    check_join_integrity,
    check_population_preserved,
    check_unique_grain,
)


def run():
    enrolled = [
        {"id": "P1", "group": "control"},
        {"id": "P2", "group": "control"},
        {"id": "P3", "group": "treatment"},
        {"id": "P4", "group": "treatment"},
        {"id": "P5", "group": "treatment"},
    ]
    exclusions = {"P5": "Synthetic example: ineligible at screening"}
    excluded = [row for row in enrolled if row["id"] in exclusions]
    eligible = [row for row in enrolled if row["id"] not in exclusions]
    analyzed = [eligible[0], eligible[1], eligible[2], eligible[2]]
    # P4 disappeared; duplicating P3 conceals that loss in the total row count.
    results = [
        check_population_preserved(enrolled, eligible + excluded, "id", check_id="screening-accounted"),
        check_population_preserved(eligible, analyzed, "id", check_id="eligible-preserved"),
        check_unique_grain(analyzed, ["id"], check_id="one-row-per-participant"),
    ]
    # Distinct participant totals, not row totals: duplication must not hide loss.
    def group_counts(rows):
        return [{"group": group, "count": len({r["id"] for r in rows if r["group"] == group})}
                for group in ("control", "treatment")]
    results.append(check_grouped_reconciliation(
        group_counts(eligible), group_counts(analyzed), keys=["group"],
        left_column="count", right_column="count", check_id="group-retention",
    ))
    # Separate join example: all eligible IDs survive but one is duplicated.
    inflated = eligible + [eligible[0]]
    results.extend([
        check_population_preserved(eligible, inflated, "id", check_id="join-population"),
        check_join_integrity(eligible, inflated, inflated, keys=["id"], check_id="inflated-join"),
        check_join_integrity(eligible, eligible, eligible, keys=["id"], check_id="valid-join"),
    ])
    return results


if __name__ == "__main__":
    for result in run():
        print(f"{result.check_id}: {result.status.upper()} — {result.message}")
    print("Synthetic evidence only: recorded exclusions do not establish scientific justification.")
