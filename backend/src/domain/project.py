from .batches import batch_score_rows
from .fixtures import DEMO_NAME, demo_rows
from .forest import score_groups
from .inputs import COLUMNS, FIELDS, normalize_rows, split_rows
from .reporting import build_report
from .thresholds import TAIL_SETTING, batch_sensitivity, tail_percentage


SPEC = {
    'columns': COLUMNS,
    'fields': FIELDS,
    'settings': [TAIL_SETTING],
    'modules': {'datasets': '控制条台账', 'runs': '暗房筛查', 'results': '换槽回查单', 'reviews': '班组复核'},
    'limitation': '每份台账适用同一显影槽、同一药液配方和同一取样工序。筛查分数供回查排序，原片放行由班组复测和签核决定。',
    'dataset_name': DEMO_NAME,
    'recommendation': '先查严格档仍越阈的换槽批次，按回查单复测槽液和控制条，再交接宽松档观察项。',
    'sampling': {
        'tree_sampling': '每棵树等概率无放回抽取不同换槽批次，再从每批随机取一条',
        'batch_score': '校准与当班均使用批内最高分控制条',
        'minimum_same_strip_count_calibration_batches': 8,
        'insufficient_batches_status': 'pending_verification',
    },
}


def analyze(rows: list[dict], settings: dict, source: dict | None = None) -> dict:
    tail_pct = tail_percentage(settings)
    groups = split_rows(normalize_rows(rows))
    scores = score_groups(groups)
    shift_scores = {row['id']: float(score) for row, score in zip(groups['shift'], scores['shift'])}
    calibration_batches = batch_score_rows(groups['reference_cal'], scores['reference_cal'])
    shift_batches = batch_score_rows(groups['shift'], scores['shift'])
    bands = batch_sensitivity(calibration_batches, shift_batches, tail_pct)
    result = build_report(
        groups,
        shift_scores,
        bands,
        calibration_batches=calibration_batches,
        shift_batches=shift_batches,
    )
    if source:
        result['source'] = {key: source[key] for key in ('version', 'checksum') if key in source}
    return result
