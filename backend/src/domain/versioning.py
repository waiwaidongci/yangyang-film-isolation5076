"""条数、分数、阈值同版校验的纯领域工具。"""
from __future__ import annotations

from .batches import basis_digest, canonical_json, sha256_json


def signing_manifest(*, row_count, scores, thresholds, strip_counts=None,
                     calibration_scores=None, source_version=None):
    digest = basis_digest(
        row_count=row_count,
        scores=scores,
        thresholds=thresholds,
        strip_counts=strip_counts,
        calibration_scores=calibration_scores,
    )
    return {
        'source_version': source_version,
        'row_count': int(row_count),
        'strip_counts': {str(k): int(v) for k, v in (strip_counts or {}).items()},
        'scores': {str(k): float(v) for k, v in sorted(scores.items())},
        'calibration_scores': {
            str(k): float(v) for k, v in sorted((calibration_scores or {}).items())
        },
        'thresholds': thresholds,
        'digest': digest,
    }


def same_signing_basis(current, candidate) -> bool:
    """候选依据可以是 digest 字符串，也可以是完整 manifest。"""
    if candidate is None:
        return True
    current_digest = current.get('digest') if isinstance(current, dict) else current
    candidate_digest = candidate if isinstance(candidate, str) else candidate.get('digest')
    if not current_digest or not candidate_digest:
        return False
    return current_digest == candidate_digest


__all__ = [
    'basis_digest',
    'canonical_json',
    'sha256_json',
    'signing_manifest',
    'same_signing_basis',
]
