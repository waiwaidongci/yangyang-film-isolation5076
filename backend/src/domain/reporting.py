import hashlib
import json

from .inputs import FEATURES, FIELDS, SPLITS
from .revisit import build_revisit_rows
from .thresholds import triage


SHIFT_LABELS = {
    'rank': '分数名次',
    'id': FIELDS['id'],
    'change_id': FIELDS['change_id'],
    'tank_id': FIELDS['tank_id'],
    'sampled_at': FIELDS['sampled_at'],
    **{key: FIELDS[key] for key in FEATURES},
    'score': '异常分数',
    'cutoff': '当前阈值',
    'margin': '分数减阈值',
    'current_hit': '当前档触发',
    'triage': '回查等级',
}
REVISIT_LABELS = {
    'queue_rank': '回查顺序',
    'priority': '回查等级',
    'change_id': FIELDS['change_id'],
    'tank_id': FIELDS['tank_id'],
    'strip_id': '主单控制条',
    'sampled_at': FIELDS['sampled_at'],
    'score': '主单分数',
    'current_hits': '批内当前档触发数',
    'strip_count': '批内控制条数',
    'route': '回查路径',
    'evidence': '实测与历史配对证据',
    'reference_strip': '最近历史控制条',
    'owner': '接单工位',
    'respond_by': '复测时限',
    'next_step': '取证复测动作',
}
SENSITIVITY_LABELS = {
    'scenario': '阈值档位',
    'tail_pct': '参考高分尾部（%）',
    'cutoff': '异常分数阈值',
    'calibration_hits': '历史校准越阈条数',
    'shift_hits': '当班越阈条数',
    'shift_rate_pct': '当班越阈比例（%）',
    'added_vs_current': '相比当前档新增',
    'removed_vs_current': '相比当前档减少',
}
SPLIT_LABELS = {
    'split': FIELDS['split'],
    'role': '用途',
    'tank_id': FIELDS['tank_id'],
    'strip_count': '控制条数',
    'change_count': '换槽批次数',
    'first_sample': '最早取样',
    'last_sample': '最晚取样',
    'snapshot_sha256': '分组快照 SHA-256',
}


def build_report(groups, shift_scores, bands):
    strict, current, loose = bands
    ranked = sorted(groups['shift'], key=lambda row: (-shift_scores[row['id']], row['id']))
    scored = [score_row(row, rank, shift_scores, bands) for rank, row in enumerate(ranked, start=1)]
    revisit = build_revisit_rows(scored, groups['reference_fit'])
    calibration_count = len(groups['reference_cal'])
    hit_count = len(current.shift_hits)
    summaries = [sensitivity_row(band, current, len(scored)) for band in bands]
    return {
        'summary': (
            f"{ranked[0]['tank_id']} 使用 {len(groups['reference_fit'])} 条冻结历史样本训练孤立森林，"
            f'以 {calibration_count} 条独立历史样本校准异常分数。当前档阈值 {current.cutoff:.6f}，'
            f'当班 {len(scored)} 条控制条有 {hit_count} 条越阈。'
            f'严格档和宽松档分别越阈 {len(strict.shift_hits)} 条和 {len(loose.shift_hits)} 条，'
            f'回查单覆盖 {len(revisit)} 个换槽批次，含宽松档观察项。'
        ),
        'metrics': {
            '历史拟合条数': len(groups['reference_fit']),
            '历史校准条数': calibration_count,
            '当前分数阈值': round(current.cutoff, 6),
            '当班越阈条数': hit_count,
            '回查与观察批次': len(revisit),
        },
        'tables': [
            table('revisit_queue', '换槽回查单', REVISIT_LABELS, revisit),
            table('shift_scores', '当班控制条分数', SHIFT_LABELS, scored),
            table('threshold_sensitivity', '阈值敏感性', SENSITIVITY_LABELS, summaries),
            table('reference_audit', '参考与当班分组快照', SPLIT_LABELS, split_audit(groups)),
        ],
        'warnings': report_warnings(current, calibration_count, bands),
    }


def score_row(row, rank, shift_scores, bands):
    record_id = row['id']
    cutoff = bands[1].cutoff
    score = shift_scores[record_id]
    return {
        'rank': rank,
        **{key: row[key] for key in ('id', 'change_id', 'tank_id', 'sampled_at', *FEATURES)},
        'score': score,
        'cutoff': cutoff,
        'margin': score - cutoff,
        'current_hit': record_id in bands[1].shift_hits,
        'triage': triage(record_id, bands),
    }


def sensitivity_row(band, current, shift_count):
    return {
        'scenario': band.label,
        'tail_pct': band.tail_pct,
        'cutoff': band.cutoff,
        'calibration_hits': band.calibration_hits,
        'shift_hits': len(band.shift_hits),
        'shift_rate_pct': round(100 * len(band.shift_hits) / shift_count, 2),
        'added_vs_current': len(band.shift_hits - current.shift_hits),
        'removed_vs_current': len(current.shift_hits - band.shift_hits),
    }


def split_audit(groups):
    roles = {
        'reference_fit': '拟合隔离树与选取配对历史控制条',
        'reference_cal': '独立校准分数阈值',
        'shift': '评分并生成换槽回查单',
    }
    return [
        {
            'split': SPLITS[split],
            'role': roles[split],
            'tank_id': rows[0]['tank_id'],
            'strip_count': len(rows),
            'change_count': len({row['change_id'] for row in rows}),
            'first_sample': min(row['sampled_at'] for row in rows),
            'last_sample': max(row['sampled_at'] for row in rows),
            'snapshot_sha256': snapshot_digest(rows),
        }
        for split, rows in groups.items()
    ]


def snapshot_digest(rows):
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def report_warnings(current, calibration_count, bands):
    warnings = ['分数用于安排回查。请核实参考组来自相同槽、配方和取样工序，再由冲洗班长给出原片放行结论。']
    if calibration_count < 40:
        warnings.append(f'历史校准只有 {calibration_count} 条，尾部分位数可能随少量记录变动，建议补齐已签核参考。')
    if any(band is not current and band.tail_pct == current.tail_pct for band in bands):
        warnings.append('参数触及敏感性边界，严格档或宽松档与当前档重合。')
    if any(band.tail_pct != current.tail_pct and band.cutoff == current.cutoff for band in bands):
        warnings.append('历史校准分数有并列，参考尾部比例变化后仍可能得到同一阈值。')
    if not current.shift_hits:
        warnings.append('当班控制条均未超过当前档阈值，请继续执行例行检片和换槽放行检查。')
    return warnings


def table(key, title, labels, rows):
    return {'key': key, 'title': title, 'columns': list(labels), 'labels': labels, 'rows': rows}
