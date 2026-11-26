from collections import defaultdict

import numpy as np

from .inputs import FEATURES


BATH_FEATURES = ('temp_c', 'conductivity_us_cm')
STRIP_FEATURES = ('base_fog_od', 'mid_density_od', 'density_spread_od')
RESPONSE_TIME = {'优先回查': '接单后 10 分钟内', '当班复查': '接单后 30 分钟内', '交班观察': '交班前'}


def build_revisit_rows(shift_scores, reference):
    by_change = defaultdict(list)
    for row in shift_scores:
        by_change[row['change_id']].append(row)

    # 分数名次已决定批次顺序。同一换槽批次以最高分控制条为主单。
    active = [rows for rows in by_change.values() if rows[0]['triage'] != '未触发']
    if not active:
        return []

    bath = np.array([[row[key] for key in BATH_FEATURES] for row in reference])
    q25, q75 = np.quantile(bath, [0.25, 0.75], axis=0)
    scales = np.maximum(q75 - q25, [0.01, 0.1])
    limits = {key: (min(row[key] for row in reference), max(row[key] for row in reference)) for key in FEATURES}
    queue = []
    for rank, rows in enumerate(active, start=1):
        primary = rows[0]
        bath_reading = [primary[key] for key in BATH_FEATURES]
        distances = np.sum(((bath - bath_reading) / scales) ** 2, axis=1)
        closest = [reference[index] for index in np.argsort(distances, kind='stable')[:5]]
        paired = {key: float(np.median([row[key] for row in closest])) for key in STRIP_FEATURES}
        route, owner, instruction = instructions(primary, limits)
        queue.append({
            'queue_rank': rank,
            'priority': primary['triage'],
            'change_id': primary['change_id'],
            'tank_id': primary['tank_id'],
            'strip_id': primary['id'],
            'sampled_at': primary['sampled_at'],
            'score': primary['score'],
            'current_hits': sum(row['current_hit'] for row in rows),
            'strip_count': len(rows),
            'route': route,
            'evidence': evidence_text(primary, limits, paired),
            'reference_strip': closest[0]['id'],
            'owner': owner,
            'respond_by': RESPONSE_TIME[primary['triage']],
            'next_step': instruction,
        })
    return queue


def instructions(row, limits):
    if outside_range(row, BATH_FEATURES, limits):
        return ('槽液双表复核', '配液值班员',
                '用独立温计和已校准电导仪复测槽液，核对补液量、配方批号和探头清洗记录；修正后复跑两条新控制条。')
    if outside_range(row, STRIP_FEATURES, limits):
        return ('控制条与密度计复核', '检片员',
                '用密度阶梯片校准后重读原控制条，复测片基和边中三点，并用同批空白控制条复跑以核查润湿和搅拌记录。')
    return ('同槽配对复测', '冲洗班长',
            '保留原控制条与配液记录，按相同浸泡时长复跑两条控制条，同时复测槽温、导电率，按近邻历史的检片读数交叉复核。')


def outside_range(row, keys, limits):
    return [key for key in keys if not limits[key][0] <= row[key] <= limits[key][1]]


def evidence_text(row, limits, paired):
    outside = outside_range(row, FEATURES, limits)
    excursions = '、'.join(
        f'{FEATURES[key][0]} {row[key]:g}（历史 {limits[key][0]:g} 至 {limits[key][1]:g}）'
        for key in outside
    )
    paired_readings = '、'.join(f'{FEATURES[key][0]} {row[key]:.3f}/{paired[key]:.3f}' for key in STRIP_FEATURES)
    prefix = f'超出拟合组观察范围 {excursions}' if outside else '五项读数均在拟合组观察范围内'
    return f'{prefix}。实测/槽温与电导近邻中位数为 {paired_readings}。'
