from dataclasses import dataclass, field

import numpy as np

from .batches import MIN_CALIBRATION_BATCHES, PENDING_TRIAGE


TAIL_SETTING = {'key': 'reference_tail_pct', 'label': '参考高分尾部（%）', 'default': 10, 'min': 5, 'max': 25, 'step': 1}
SWEEP_STEP = 5


@dataclass(frozen=True)
class Sensitivity:
    label: str
    tail_pct: int
    cutoff: float | None
    calibration_hits: int
    shift_hits: frozenset[str]
    cutoffs: dict[int, float | None] = field(default_factory=dict)
    change_hits: frozenset[str] = frozenset()
    strata: tuple[dict, ...] = ()
    pending_counts: tuple[int, ...] = ()
    pending_changes: frozenset[str] = frozenset()


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
    """旧版全样本全局阈值，保留给直接调用该函数的检查。"""
    calibration_scores = np.asarray(calibration_scores, dtype=float)
    bands = []
    for label, percentile_tail in (
        ('严格档', max(TAIL_SETTING['min'], tail_pct - SWEEP_STEP)),
        ('当前档', tail_pct),
        ('宽松档', min(TAIL_SETTING['max'], tail_pct + SWEEP_STEP)),
    ):
        cutoff = float(np.quantile(calibration_scores, 1 - percentile_tail / 100, method='linear'))
        hits = frozenset(record_id for record_id, score in shift_scores.items() if score > cutoff)
        bands.append(Sensitivity(
            label=label,
            tail_pct=percentile_tail,
            cutoff=cutoff,
            calibration_hits=int(np.count_nonzero(calibration_scores > cutoff)),
            shift_hits=hits,
        ))
    return tuple(bands)


def batch_sensitivity(calibration_batches, shift_batches, tail_pct):
    """按“批内最高分”和相同控制条条数分层定阈。"""
    cal_by_count: dict[int, list[dict]] = {}
    shift_by_count: dict[int, list[dict]] = {}
    for batch in calibration_batches:
        cal_by_count.setdefault(int(batch['strip_count']), []).append(batch)
    for batch in shift_batches:
        shift_by_count.setdefault(int(batch['strip_count']), []).append(batch)

    all_counts = sorted(set(cal_by_count) | set(shift_by_count))
    bands = []
    for label, percentile_tail in (
        ('严格档', max(TAIL_SETTING['min'], tail_pct - SWEEP_STEP)),
        ('当前档', tail_pct),
        ('宽松档', min(TAIL_SETTING['max'], tail_pct + SWEEP_STEP)),
    ):
        cutoffs: dict[int, float | None] = {}
        strata: list[dict] = []
        shift_hits: set[str] = set()
        change_hits: set[str] = set()
        pending_counts: set[int] = set()
        pending_changes: set[str] = set()
        calibration_hits = 0

        for strip_count in all_counts:
            cal_batches = cal_by_count.get(strip_count, [])
            count_shift_batches = shift_by_count.get(strip_count, [])
            cal_values = np.asarray([batch['score'] for batch in cal_batches], dtype=float)
            stratum_shift_hits: set[str] = set()
            stratum_change_hits: set[str] = set()

            if len(cal_batches) < MIN_CALIBRATION_BATCHES:
                pending_counts.add(strip_count)
                pending_changes.update(batch['change_id'] for batch in count_shift_batches)
                status = 'pending_verification'
                cutoff = None
                stratum_cal_hits = 0
            else:
                cutoff = float(np.quantile(
                    cal_values, 1 - percentile_tail / 100, method='linear'))
                stratum_cal_hits = int(np.count_nonzero(cal_values > cutoff))
                calibration_hits += stratum_cal_hits
                for batch in count_shift_batches:
                    if float(batch['score']) > cutoff:
                        stratum_shift_hits.add(batch['strip_id'])
                        stratum_change_hits.add(batch['change_id'])
                shift_hits.update(stratum_shift_hits)
                change_hits.update(stratum_change_hits)
                status = 'ready'

            # 阈值映射只服务当班批次；纯校准层仍保留在 strata 审计信息中。
            if count_shift_batches:
                cutoffs[strip_count] = cutoff

            strata.append({
                'strip_count': strip_count,
                'status': status,
                'cutoff': cutoff,
                'calibration_batches': len(cal_batches),
                'minimum_calibration_batches': MIN_CALIBRATION_BATCHES,
                'calibration_hits': stratum_cal_hits,
                'shift_batches': len(count_shift_batches),
                'shift_hits': len(stratum_shift_hits),
                'shift_hit_strip_ids': sorted(stratum_shift_hits),
                'shift_hit_change_ids': sorted(stratum_change_hits),
            })

        ready_cutoffs = [value for value in cutoffs.values() if value is not None]
        scalar_cutoff = ready_cutoffs[0] if len(cutoffs) == 1 and ready_cutoffs else None
        bands.append(Sensitivity(
            label=label,
            tail_pct=percentile_tail,
            cutoff=scalar_cutoff,
            calibration_hits=calibration_hits,
            shift_hits=frozenset(shift_hits),
            cutoffs=cutoffs,
            change_hits=frozenset(change_hits),
            strata=tuple(strata),
            pending_counts=tuple(sorted(pending_counts)),
            pending_changes=frozenset(pending_changes),
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


def batch_triage(batch, bands):
    strict, current, loose = bands
    strip_count = int(batch['strip_count'])
    if current.cutoffs and strip_count in current.cutoffs:
        current_cutoff = current.cutoffs[strip_count]
        strict_cutoff = (strict.cutoffs or {}).get(strip_count)
        loose_cutoff = (loose.cutoffs or {}).get(strip_count)
    else:
        # 兼容旧版全局单层 Sensitivity。
        current_cutoff = current.cutoff
        strict_cutoff = strict.cutoff
        loose_cutoff = loose.cutoff
    if current_cutoff is None:
        return PENDING_TRIAGE

    score = float(batch['score'])
    if strict_cutoff is not None and score > strict_cutoff:
        return '优先回查' if strict.tail_pct < current.tail_pct else '当班复查'
    if score > current_cutoff:
        return '当班复查'
    if loose_cutoff is not None and score > loose_cutoff:
        return '交班观察'
    return '未触发'


same_count_sensitivity = batch_sensitivity
stratified_sensitivity = batch_sensitivity
batch_thresholds = batch_sensitivity
