ROLE_PASSENGER         = "passenger"
ROLE_TRAIN_VERIFIER    = "train_verifier"
ROLE_ISSUER_VERIFIER   = "issuer_verifier"
ROLE_UNIVERSITY_AGENT  = "university_agent"


def normalize_role(role: str | None) -> str:
    role = (role or "").strip().lower()
    if role == "conductor":
        return ROLE_TRAIN_VERIFIER
    if role == "admin":
        return ROLE_ISSUER_VERIFIER
    if role == "university_agent":
        return ROLE_UNIVERSITY_AGENT
    return role


def has_role(role: str | None, expected: str) -> bool:
    return normalize_role(role) == expected
