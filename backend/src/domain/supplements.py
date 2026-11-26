from .inputs import normalize_rows


def merge_late_calibration(existing: list[dict], additions: list[dict]) -> list[dict]:
    """把晚到校准记录补进已经存在的 reference_cal 换槽批次。"""
    if not additions:
        raise ValueError('晚到校准记录至少需要一条')

    existing_ids = {row['id'] for row in existing}
    cal_changes = {
        row['change_id']
        for row in existing
        if row.get('split') == 'reference_cal'
    }
    addition_ids = set()
    for line, row in enumerate(additions, start=2):
        if not row.get('split'):
            row['split'] = 'reference_cal'
        split = row.get('split')
        if split != 'reference_cal':
            raise ValueError(f'补录文件第 {line} 行必须是 reference_cal 历史校准记录')
        record_id = row.get('id')
        change_id = row.get('change_id')
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError(f'补录文件第 {line} 行缺少控制条编号')
        if record_id in existing_ids or record_id in addition_ids:
            raise ValueError(f'晚到校准控制条编号重复：{record_id}')
        addition_ids.add(record_id)
        if change_id not in cal_changes:
            raise ValueError(f'晚到校准记录必须补进原历史校准批，找不到批次 {change_id}')

    return normalize_rows([*existing, *additions])
