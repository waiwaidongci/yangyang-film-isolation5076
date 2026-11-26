import math
import re
from datetime import datetime


SPLITS = {
    'reference_fit': '历史拟合',
    'reference_cal': '历史校准',
    'shift': '当班待筛',
}
MIN_ROWS = {'reference_fit': 32, 'reference_cal': 24, 'shift': 1}
FEATURES = {
    'temp_c': ('槽液温度（°C）', 10.0, 35.0),
    'conductivity_us_cm': ('槽液导电率（µS/cm）', 50.0, 5000.0),
    'base_fog_od': ('片基灰雾（OD）', 0.0, 1.5),
    'mid_density_od': ('中灰阶密度（OD）', 0.05, 4.0),
    'density_spread_od': ('边心密度差（OD）', 0.0, 2.0),
}
FIELDS = {
    'id': '控制条编号',
    'split': '样本分组',
    'tank_id': '显影槽编号',
    'change_id': '换槽批次',
    'sampled_at': '取样时间（本地）',
    **{key: label for key, (label, _, _) in FEATURES.items()},
}
COLUMNS = list(FIELDS)
CODE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}')
TIMESTAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}')


def normalize_rows(rows: list[dict]) -> list[dict]:
    if not rows or len(rows) > 5000:
        raise ValueError('台账须包含 1 至 5000 行记录')

    normalized = []
    seen_ids = set()
    change_splits = {}
    tank_id = None
    for line, row in enumerate(rows, start=2):
        if not isinstance(row, dict) or row.keys() != FIELDS.keys():
            raise ValueError(f'CSV 第 {line} 行列名不符，应为 {", ".join(COLUMNS)}')
        split = row['split'].strip() if isinstance(row['split'], str) else ''
        if split not in SPLITS:
            raise ValueError(f'CSV 第 {line} 行的分组须为 {", ".join(SPLITS)} 之一')
        record = {key: read_code(row[key], key, line) for key in ('id', 'tank_id', 'change_id')}
        if record['id'] in seen_ids:
            raise ValueError(f"CSV 第 {line} 行控制条编号重复：{record['id']}")
        seen_ids.add(record['id'])
        if tank_id is None:
            tank_id = record['tank_id']
        if record['tank_id'] != tank_id:
            raise ValueError(f'CSV 第 {line} 行显影槽与本台账的 {tank_id} 不同，请按槽分别导入')
        if change_splits.setdefault(record['change_id'], split) != split:
            raise ValueError(f"换槽批次 {record['change_id']} 跨分组，请把同批控制条放在同一组")
        record['split'] = split
        record['sampled_at'] = read_timestamp(row['sampled_at'], line)
        record.update({key: read_measurement(row[key], key, line) for key in FEATURES})
        normalized.append({key: record[key] for key in COLUMNS})

    groups = split_rows(normalized)
    for split, minimum in MIN_ROWS.items():
        if len(groups[split]) < minimum:
            raise ValueError(f'{SPLITS[split]}至少需要 {minimum} 条控制条记录，当前 {len(groups[split])} 条')
    for earlier, later in zip(SPLITS, tuple(SPLITS)[1:]):
        if max(row['sampled_at'] for row in groups[earlier]) >= min(row['sampled_at'] for row in groups[later]):
            raise ValueError(f'{SPLITS[earlier]}的所有取样时间须早于{SPLITS[later]}组')
    return normalized


def split_rows(rows):
    groups = {key: [] for key in SPLITS}
    for row in sorted(rows, key=lambda record: record['id']):
        groups[row['split']].append(row)
    return groups


def read_code(value, key, line):
    value = value.strip() if isinstance(value, str) else ''
    if not CODE.fullmatch(value):
        raise ValueError(f'CSV 第 {line} 行 {FIELDS[key]}须以字母或数字开头，限 1–48 位字母、数字、连字符或下划线')
    return value


def read_timestamp(value, line):
    value = value.strip() if isinstance(value, str) else ''
    if TIMESTAMP.fullmatch(value):
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            pass
    raise ValueError(f'CSV 第 {line} 行取样时间须为有效的 YYYY-MM-DD HH:MM 本地时间')


def read_measurement(value, key, line):
    label, lower, upper = FEATURES[key]
    try:
        number = float(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else math.nan
    except (ValueError, OverflowError):
        number = math.nan
    if not math.isfinite(number) or not lower <= number <= upper:
        raise ValueError(f'CSV 第 {line} 行 {label}须为 {lower:g} 至 {upper:g} 的有限数字')
    return number if number else 0.0
