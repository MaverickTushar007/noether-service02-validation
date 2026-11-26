"""Compare frozen client fields with independent reviewer records."""
from decimal import Decimal

# Match if absolute error <= atol + rtol * abs(client). Dates and labels must match exactly.
PRICE = Decimal("1e-10")
CASH = Decimal("1e-8")
SHARES = Decimal("1e-9")
METRIC = Decimal("1e-12")
RELATIVE = Decimal("1e-12")


def compare(section, client, reviewer, fields, key):
    """Compare in recorded order, preserving missing rows and recording the first mismatch."""
    output = []
    for field, tolerance in fields.items():
        max_abs = max_rel = Decimal(0)
        worst_date = first_mismatch = ""
        relative_count = numeric_count = failures = 0
        for index in range(max(len(client), len(reviewer))):
            left = client[index] if index < len(client) else None
            right = reviewer[index] if index < len(reviewer) else None
            location = str((right or left).get(key, index + 1))
            if left is None or right is None or field not in left or field not in right:
                equal = False
            else:
                reference, observed = str(left[field]), str(right[field])
                if tolerance is None or reference == "" or observed == "":
                    equal = reference == observed
                else:
                    reference, observed = Decimal(reference), Decimal(observed)
                    difference = abs(observed - reference)
                    numeric_count += 1
                    if difference > max_abs:
                        max_abs, worst_date = difference, location
                    if reference:
                        relative_count += 1
                        max_rel = max(max_rel, difference / abs(reference))
                    equal = difference <= tolerance + RELATIVE * abs(reference)
            if not equal:
                failures += 1
                first_mismatch = first_mismatch or location
        output.append({
            "section": section, "field": field, "status": "FAIL" if failures else "PASS",
            "client_rows": len(client), "reviewer_rows": len(reviewer), "mismatches": failures,
            "first_mismatch_key": first_mismatch, "max_abs_difference": max_abs if numeric_count else "",
            "max_abs_key": worst_date, "max_rel_difference": max_rel if relative_count else "",
            "nonzero_client_numeric_values": relative_count,
            "absolute_tolerance": "" if tolerance is None else tolerance,
            "relative_tolerance": "" if tolerance is None else RELATIVE,
        })
    return output
