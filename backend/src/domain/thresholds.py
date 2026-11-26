from dataclasses import dataclass

import numpy as np


TAIL_SETTING = {'key': 'reference_tail_pct', 'label': '参考高分尾部（%）', 'default': 10, 'min': 5, 'max': 25, 'step': 1}
SWEEP_STEP = 5


@dataclass(frozen=True)
class Sensitivity:
    label: str
    tail_pct: int
    cutoff: float
    calibration_hits: int
    shift_hits: frozenset[str]


def tail_percentage(settings):
    key = TAIL_SETTING['key']
    if settings.keys() - {key}:
        raise ValueError('存在未定义的换槽巡检参数')
    value = settings.get(key, TAIL_SETTING['default'])
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not TAIL_SETTING['min'] <= value <= TAIL_SETTING['max'] or value != int(value)):
        raise ValueError(f"{TAIL_SETTING['label']}须为 {TAIL_SETTING['min']} 至 {TAIL_SETTING['max']} 的整数")
    return int(value)


def sensitivity(calibration_scores, shift_scores, tail_pct):
    calibration_scores = np.asarray(calibration_scores, dtype=float)
    bands = []
    for label, percentile_tail in (
        ('严格档', max(TAIL_SETTING['min'], tail_pct - SWEEP_STEP)),
        ('当前档', tail_pct),
        ('宽松档', min(TAIL_SETTING['max'], tail_pct + SWEEP_STEP)),
    ):
        cutoff = float(np.quantile(calibration_scores, 1 - percentile_tail / 100, method='linear'))
        bands.append(Sensitivity(
            label=label,
            tail_pct=percentile_tail,
            cutoff=cutoff,
            calibration_hits=int(np.count_nonzero(calibration_scores > cutoff)),
            shift_hits=frozenset(record_id for record_id, score in shift_scores.items() if score > cutoff),
        ))
    return tuple(bands)


def triage(record_id, bands):
    strict, current, loose = bands
    if record_id in strict.shift_hits:
        return '优先回查' if strict.tail_pct < current.tail_pct else '当班复查'
    if record_id in current.shift_hits:
        return '当班复查'
    if record_id in loose.shift_hits:
        return '交班观察'
    return '未触发'
