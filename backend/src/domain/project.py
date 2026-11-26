from .fixtures import DEMO_NAME, demo_rows
from .forest import score_groups
from .inputs import COLUMNS, FIELDS, normalize_rows, split_rows
from .reporting import build_report
from .thresholds import TAIL_SETTING, sensitivity, tail_percentage


SPEC = {
    'columns': COLUMNS,
    'fields': FIELDS,
    'settings': [TAIL_SETTING],
    'modules': {'datasets': '控制条台账', 'runs': '暗房筛查', 'results': '换槽回查单', 'reviews': '班组复核'},
    'limitation': '每份台账适用同一显影槽、同一药液配方和同一取样工序。筛查分数供回查排序，原片放行由班组复测和签核决定。',
    'dataset_name': DEMO_NAME,
    'recommendation': '先查严格档仍越阈的换槽批次，按回查单复测槽液和控制条，再交接宽松档观察项。',
}


def analyze(rows: list[dict], settings: dict) -> dict:
    tail_pct = tail_percentage(settings)
    groups = split_rows(normalize_rows(rows))
    scores = score_groups(groups)
    shift_scores = {row['id']: float(score) for row, score in zip(groups['shift'], scores['shift'])}
    bands = sensitivity(scores['reference_cal'], shift_scores, tail_pct)
    return build_report(groups, shift_scores, bands)
