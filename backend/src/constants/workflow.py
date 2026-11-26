from enum import StrEnum


class Role(StrEnum):
    ADMIN = 'admin'
    ANALYST = 'analyst'
    VIEWER = 'viewer'


class RunStatus(StrEnum):
    COMPLETED = 'completed'
    FAILED = 'failed'
    PENDING = 'pending'
    PENDING_VERIFICATION = 'pending_verification'
    STALE = 'stale'


class Decision(StrEnum):
    APPROVED = 'approved'
    REJECTED = 'rejected'
