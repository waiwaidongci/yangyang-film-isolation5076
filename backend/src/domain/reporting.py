import hashlib
import json

from .batches import PENDING_TRIAGE, basis_digest
from .inputs import FEATURES, FIELDS, SPLITS
from .revisit import build_revisit_rows
from .thresholds import batch_triage


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
    # 新增字段统一追加，保持旧 CSV 列顺序稳定。
    'strip_count': '批内控制条数',
    'batch_primary': '批内主单',
    'above_cutoff': '该条超过阈值',
    'batch_hit': '本批当前档触发',
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
    'calibration_hits': '历史校准越阈数',
    'shift_hits': '当班越阈数',
    'shift_rate_pct': '当班越阈比例（%）',
    'added_vs_current': '相比当前档新增',
    'removed_vs_current': '相比当前档减少',
    # 批次口径新增列追加在后面。
    'strip_count': '同条数校准批的控制条数',
    'status': '定线状态',
    'calibration_batches': '历史校准批次数',
    'shift_batches': '当班批次数',
}
PENDING_LABELS = {
    'change_id': FIELDS['change_id'],
    'tank_id': FIELDS['tank_id'],
    'strip_id': '批内最高分控制条',
    'sampled_at': FIELDS['sampled_at'],
    'strip_count': '批内控制条数',
    'score': '批内最高分',
    'calibration_batches': '同条数历史校准批数',
    'minimum_calibration_batches': '最低校准批数',
    'status': '状态',
    'reason': '待核原因',
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


def public_batch(batch):
    return {key: value for key, value in batch.items() if key != 'row'}


def build_report(groups, shift_scores, bands, calibration_batches=None, shift_batches=None):
    strict, current, loose = bands
    if shift_batches is None:
        from .batches import batch_score_rows
        shift_batches = batch_score_rows(groups['shift'], shift_scores)
    batch_by_change = {batch['change_id']: batch for batch in shift_batches}

    ranked = sorted(groups['shift'], key=lambda row: (-shift_scores[row['id']], row['id']))
    scored = [
        score_row(row, rank, shift_scores, bands, batch_by_change[row['change_id']])
        for rank, row in enumerate(ranked, start=1)
    ]
    revisit = build_revisit_rows(scored, groups['reference_fit'])
    pending = pending_rows(shift_batches, current)

    calibration_count = len(groups['reference_cal'])
    calibration_batch_count = len({row['change_id'] for row in groups['reference_cal']})
    shift_batch_count = len(shift_batches)
    hit_count = len(current.shift_hits)
    pending_count = len(current.pending_changes)
    verification_status = 'pending_verification' if pending_count else 'verified'

    representative_cutoff = None
    ready_cutoffs = [value for value in (current.cutoffs or {}).values() if value is not None]
    if len(set(ready_cutoffs)) == 1:
        representative_cutoff = ready_cutoffs[0]
    threshold_text = (
        f'当前档阈值 {representative_cutoff:.6f}' if representative_cutoff is not None
        else '当前档按批内条数分别定阈'
    )
    summary = (
        f"{ranked[0]['tank_id']} 使用 {len(groups['reference_fit'])} 条冻结历史样本、"
        f'{len({row["change_id"] for row in groups["reference_fit"]})} 个换槽批次训练批次均衡孤立森林，'
        f'以 {calibration_count} 条、{calibration_batch_count} 个历史校准批的批内最高分校准异常分数。'
        f'{threshold_text}，当班 {len(scored)} 条控制条、{shift_batch_count} 个换槽批次中 '
        f'{hit_count} 个批次越阈。'
        f'严格档和宽松档分别越阈 {len(strict.shift_hits)} 批和 {len(loose.shift_hits)} 批，'
        f'回查单覆盖 {len(revisit)} 个换槽批次，含宽松档观察项；{pending_count} 批待核。'
    )

    sensitivity = sensitivity_tables(bands)
    basis = build_basis(groups, shift_scores, current, calibration_batches)
    tables = [
        table('revisit_queue', '换槽回查单', REVISIT_LABELS, revisit),
        table('shift_scores', '当班控制条分数', SHIFT_LABELS, scored),
        table('threshold_sensitivity', '阈值敏感性', SENSITIVITY_LABELS, sensitivity),
        table('reference_audit', '参考与当班分组快照', SPLIT_LABELS, split_audit(groups)),
    ]
    if pending:
        tables.insert(3, table('pending_verification', '校准不足待核批次', PENDING_LABELS, pending))

    return {
        'summary': summary,
        'status': 'pending' if pending_count else 'completed',
        'verification_status': verification_status,
        'adjudication_status': '待核' if pending_count else '可签核',
        'metrics': {
            '历史拟合条数': len(groups['reference_fit']),
            '历史校准条数': calibration_count,
            '历史校准批次数': calibration_batch_count,
            '当班批次数': shift_batch_count,
            '当前分数阈值': round(representative_cutoff, 6) if representative_cutoff is not None else None,
            '当班越阈条数': hit_count,
            '当班越阈批次数': hit_count,
            '待核批次数': pending_count,
            '回查与观察批次': len(revisit),
        },
        'basis': basis,
        'thresholds': threshold_manifest(bands),
        'batches': {
            'reference_cal': [public_batch(batch) for batch in (calibration_batches or [])],
            'shift': [public_batch(batch) for batch in shift_batches],
        },
        'pending_batches': pending,
        'pending_verification': pending,
        'batch_policy': {
            'score_sample': '每批取最高分控制条',
            'calibration_line': '仅使用与当班批次控制条条数相同的历史校准批',
            'minimum_calibration_batches': 8,
        },
        'tables': tables,
        'warnings': report_warnings(current, calibration_count, calibration_batch_count, bands),
    }


def score_row(row, rank, shift_scores, bands, batch):
    record_id = row['id']
    current = bands[1]
    score = shift_scores[record_id]
    strip_count = int(batch['strip_count'])
    cutoff = (current.cutoffs or {}).get(strip_count, current.cutoff)
    triage_value = batch_triage(batch, bands)
    return {
        'rank': rank,
        **{key: row[key] for key in ('id', 'change_id', 'tank_id', 'sampled_at', *FEATURES)},
        'strip_count': strip_count,
        'batch_primary': record_id == batch['strip_id'],
        'score': score,
        'cutoff': cutoff,
        'margin': score - cutoff if cutoff is not None else None,
        'above_cutoff': cutoff is not None and score > cutoff,
        'current_hit': record_id in current.shift_hits,
        'batch_hit': batch['strip_id'] in current.shift_hits,
        'triage': triage_value,
    }


def sensitivity_tables(bands):
    current = bands[1]
    current_strata = {item['strip_count']: item for item in current.strata}
    rows = []
    for band in bands:
        for stratum in band.strata:
            if stratum['shift_batches'] <= 0:
                continue
            current_stratum = current_strata[stratum['strip_count']]
            current_ids = set(current_stratum['shift_hit_strip_ids'])
            band_ids = set(stratum['shift_hit_strip_ids'])
            shift_count = stratum['shift_batches']
            rows.append({
                'scenario': band.label,
                'tail_pct': band.tail_pct,
                'strip_count': stratum['strip_count'],
                'status': '可定线' if stratum['status'] == 'ready' else '待核',
                'cutoff': stratum['cutoff'],
                'calibration_batches': stratum['calibration_batches'],
                'calibration_hits': stratum['calibration_hits'],
                'shift_batches': shift_count,
                'shift_hits': stratum['shift_hits'],
                'shift_rate_pct': round(100 * stratum['shift_hits'] / shift_count, 2) if shift_count else 0.0,
                'added_vs_current': len(band_ids - current_ids),
                'removed_vs_current': len(current_ids - band_ids),
            })
    return rows


def pending_rows(shift_batches, current):
    strata = {item['strip_count']: item for item in current.strata}
    rows = []
    for batch in sorted(shift_batches, key=lambda item: (-item['score'], item['strip_id'])):
        strip_count = int(batch['strip_count'])
        stratum = strata.get(strip_count, {})
        if strip_count not in current.pending_counts:
            continue
        rows.append({
            'change_id': batch['change_id'],
            'tank_id': batch.get('tank_id'),
            'strip_id': batch['strip_id'],
            'sampled_at': batch.get('sampled_at'),
            'strip_count': strip_count,
            'score': batch['score'],
            'calibration_batches': stratum.get('calibration_batches', 0),
            'minimum_calibration_batches': stratum.get('minimum_calibration_batches', 8),
            'status': PENDING_TRIAGE,
            'reason': f'与本批同为 {strip_count} 条控制条的历史校准批不足 8 批，不能同条数定线',
        })
    return rows


def threshold_manifest(bands):
    strict, current, loose = bands
    result = []
    for strip_count in sorted((current.cutoffs or {}).keys()):
        current_stratum = next(
            (item for item in current.strata if item['strip_count'] == strip_count), {}
        )
        result.append({
            'strip_count': strip_count,
            'status': current_stratum.get('status', 'ready'),
            'strict_tail_pct': strict.tail_pct,
            'strict_cutoff': (strict.cutoffs or {}).get(strip_count, strict.cutoff),
            'current_tail_pct': current.tail_pct,
            'current_cutoff': (current.cutoffs or {}).get(strip_count, current.cutoff),
            'loose_tail_pct': loose.tail_pct,
            'loose_cutoff': (loose.cutoffs or {}).get(strip_count, loose.cutoff),
            'calibration_batches': current_stratum.get('calibration_batches'),
        })
    return result


def build_basis(groups, shift_scores, current, calibration_batches=None):
    strip_counts = {
        change_id: len(rows)
        for change_id, rows in _group_changes(groups['shift']).items()
    }
    calibration_scores = {
        batch['strip_id']: batch['score']
        for batch in (calibration_batches or [])
    }
    thresholds = {
        'tail_pct': current.tail_pct,
        'cutoff': current.cutoff,
        'cutoffs': {str(key): value for key, value in (current.cutoffs or {}).items()},
    }
    row_count = sum(len(rows) for rows in groups.values())
    digest = basis_digest(
        row_count=row_count,
        scores=shift_scores,
        thresholds=thresholds,
        strip_counts=strip_counts,
        calibration_scores=calibration_scores,
    )
    return {
        'version': 1,
        'digest': digest,
        'row_count': row_count,
        'strip_counts': strip_counts,
        'scores': shift_scores,
        'calibration_scores': calibration_scores,
        **thresholds,
    }


def _group_changes(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row['change_id'], []).append(row)
    return grouped


def split_audit(groups):
    roles = {
        'reference_fit': '拟合隔离树与选取配对历史控制条',
        'reference_cal': '按批内最高分和同条数批次校准阈值',
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


def report_warnings(current, calibration_count, calibration_batch_count, bands):
    warnings = ['分数用于安排回查。请核实参考组来自相同槽、配方和取样工序，再由冲洗班长给出原片放行结论。']
    if current.pending_changes:
        counts = '、'.join(str(count) for count in current.pending_counts)
        warnings.append(
            f'控制条数为 {counts} 的当班批次缺少至少 8 个同条数历史校准批，相关批次标记待核，不得按当前阈值签核。'
        )
    if calibration_batch_count < 8:
        warnings.append(f'历史校准总共只有 {calibration_batch_count} 批，尾部分位数可能随少量批次变动，建议补齐已签核参考。')
    elif calibration_count < 40:
        warnings.append(f'历史校准只有 {calibration_count} 条记录，已按批次最高分和同条数批次定线。')
    if any(band is not current and band.tail_pct == current.tail_pct for band in bands):
        warnings.append('参数触及敏感性边界，严格档或宽松档与当前档重合。')
    if any(band.tail_pct != current.tail_pct and _has_tie_cutoff(band, current) for band in bands):
        warnings.append('历史校准批次最高分有并列，参考尾部比例变化后仍可能得到同一阈值。')
    if not current.shift_hits and not current.pending_changes:
        warnings.append('当班批次均未超过当前档阈值，请继续执行例行检片和换槽放行检查。')
    return warnings


def _has_tie_cutoff(band, current):
    for count, cutoff in (band.cutoffs or {}).items():
        other = (current.cutoffs or {}).get(count)
        if cutoff is not None and other is not None and cutoff == other:
            return True
    return False


def table(key, title, labels, rows):
    return {'key': key, 'title': title, 'columns': list(labels), 'labels': labels, 'rows': rows}
