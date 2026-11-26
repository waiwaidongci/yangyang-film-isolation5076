from datetime import datetime, timedelta
from random import Random


DEMO_NAME = 'DH-02_黑白显影换槽控制条_20261125.csv'
TANK_ID = 'DH-02'
SEED = 261125


def demo_rows() -> list[dict]:
    rng = Random(SEED)
    rows = []
    periods = (
        ('reference_fit', 10, 10, 6),
        ('reference_cal', 20, 4, 6),
        ('shift', 25, 1, 12),
    )
    for split, day_start, day_count, changes in periods:
        for day in range(day_start, day_start + day_count):
            start = datetime(2026, 11, day, 8)
            for change in range(1, changes + 1):
                process = rng.uniform(-1, 1)
                replenishment = rng.uniform(-1, 1)
                change_id = f'DH02-{start:%y%m%d}-{change:02d}'
                for index, strip in enumerate('AB'):
                    sampled_at = start + timedelta(minutes=(change - 1) * 30 + 5 + index * 3)
                    measurements = stable_measurements(rng, process, replenishment)
                    if split == 'shift':
                        measurements.update(shift_incidents(change, strip))
                    rows.append({
                        'id': f'{change_id}-{strip}',
                        'split': split,
                        'tank_id': TANK_ID,
                        'change_id': change_id,
                        'sampled_at': sampled_at.strftime('%Y-%m-%d %H:%M'),
                        **measurements,
                    })
    return rows


def stable_measurements(rng, process, replenishment):
    # A/B 控制条共享配液和槽温条件，读数保留各自的测量波动。
    return {
        'temp_c': round(20.0 + 0.42 * process + rng.gauss(0, 0.045), 2),
        'conductivity_us_cm': round(980 + 64 * replenishment + 26 * process + rng.gauss(0, 5), 1),
        'base_fog_od': round(0.175 + 0.023 * replenishment + 0.008 * process + rng.gauss(0, 0.003), 3),
        'mid_density_od': round(0.94 + 0.094 * process + 0.024 * replenishment + rng.gauss(0, 0.006), 3),
        'density_spread_od': round(0.037 + 0.012 * replenishment - 0.005 * process + rng.gauss(0, 0.002), 3),
    }


def shift_incidents(change, strip):
    if change == 1 and strip == 'B':
        return {'mid_density_od': 0.936}
    if change == 2 and strip == 'A':
        return {'density_spread_od': 0.042}
    if change == 3:
        return {
            'temp_c': 20.37,
            'conductivity_us_cm': 1041.0,
            'base_fog_od': 0.154,
            'mid_density_od': 0.853 if strip == 'A' else 0.864,
            'density_spread_od': 0.052,
        }
    if change == 4 and strip == 'A':
        return {'mid_density_od': 0.850}
    if change == 7:
        return {'conductivity_us_cm': 1330.0 if strip == 'A' else 1290.0, 'temp_c': 21.10}
    if change == 9 and strip == 'A':
        return {'density_spread_od': 0.105, 'base_fog_od': 0.237}
    return {}
