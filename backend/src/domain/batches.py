"""换槽批次聚合与判定依据工具。"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable

import numpy as np


MIN_CALIBRATION_BATCHES = 8
PENDING_TRIAGE = '待核'


def batch_id_order(rows: Iterable[dict]) -> list[str]:
    return sorted({row['change_id'] for row in rows})


def group_by_change(rows: Iterable[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row['change_id']].append(row)
    for change_id in grouped:
        grouped[change_id].sort(key=lambda row: row['id'])
    return dict(grouped)


def primary_row(rows: list[dict], scores: dict[str, float] | None = None) -> dict:
    """返回批内最高分控制条；同分时取编号较小者。"""
    if scores is None:
        return sorted(rows, key=lambda row: row['id'])[0]
    best_score = max(float(scores[row['id']]) for row in rows)
    candidates = [row for row in rows if float(scores[row['id']]) == best_score]
    return sorted(candidates, key=lambda row: row['id'])[0]


def batch_score_rows(rows: Iterable[dict], scores) -> list[dict]:
    """把逐条分数压缩为每批一个最高分样本。

    ``scores`` 可以是与 ``rows`` 对齐的数组，也可以是以控制条编号为键的映射。
    """
    rows = list(rows)
    if isinstance(scores, dict):
        score_by_id = {key: float(value) for key, value in scores.items()}
    else:
        score_by_id = {row['id']: float(score) for row, score in zip(rows, np.asarray(scores, dtype=float))}

    result = []
    grouped = group_by_change(rows)
    for change_id in sorted(grouped):
        batch_rows = grouped[change_id]
        primary = primary_row(batch_rows, score_by_id)
        result.append({
            'change_id': change_id,
            'strip_id': primary['id'],
            'tank_id': primary.get('tank_id'),
            'sampled_at': primary.get('sampled_at'),
            'strip_count': len(batch_rows),
            'score': score_by_id[primary['id']],
            'row': primary,
        })
    return result


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256_json(value) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


batch_max_scores = batch_score_rows
primary_batch_row = primary_row


def basis_digest(*, row_count: int, scores: dict, thresholds: dict,
                 strip_counts: dict | None = None,
                 calibration_scores: dict | None = None) -> str:
    """条数、分数和阈值的同版摘要。"""
    manifest = {
        'row_count': int(row_count),
        'strip_counts': {str(key): int(value) for key, value in sorted((strip_counts or {}).items())},
        'scores': {str(key): float(value) for key, value in sorted(scores.items())},
        'calibration_scores': {
            str(key): float(value)
            for key, value in sorted((calibration_scores or {}).items())
        },
        'thresholds': json.loads(canonical_json(thresholds)),
    }
    return sha256_json(manifest)
