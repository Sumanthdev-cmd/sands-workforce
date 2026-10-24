def has_remuneration(structure):
    """Fixed deduction or zero take-home must not decide salary eligibility."""
    return structure is not None and any(float(getattr(structure, key, 0) or 0) > 0
        for key in ("basic_salary", "hra", "conveyance_allowance", "other_allowance", "daily_allowance"))
