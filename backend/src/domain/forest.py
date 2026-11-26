import numpy as np
from sklearn.ensemble import IsolationForest

from .inputs import FEATURES


FOREST_SEED = 261125
TREE_COUNT = 256
SAMPLE_LIMIT = 128


def feature_matrix(rows):
    return np.asarray([[row[key] for key in FEATURES] for row in rows], dtype=np.float32)


def score_groups(groups):
    fit = feature_matrix(groups['reference_fit'])
    if np.count_nonzero(np.ptp(fit, axis=0)) < 2:
        raise ValueError('历史拟合组至少需要两项读数有变化，请核对是否导入了重复或占位读数')
    if len(np.unique(fit, axis=0)) < 16:
        raise ValueError('历史拟合组至少需要 16 种不同的读数组合，请补充独立取样')
    forest = IsolationForest(
        n_estimators=TREE_COUNT,
        max_samples=min(SAMPLE_LIMIT, len(fit)),
        max_features=1.0,
        contamination='auto',
        random_state=FOREST_SEED,
        n_jobs=1,
    )
    forest.fit(fit)
    return {
        split: -forest.score_samples(feature_matrix(groups[split]))
        for split in ('reference_cal', 'shift')
    }
