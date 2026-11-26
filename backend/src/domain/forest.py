import numpy as np
from sklearn.ensemble import IsolationForest

from .inputs import FEATURES


FOREST_SEED = 261125
TREE_COUNT = 256
SAMPLE_LIMIT = 128


def feature_matrix(rows):
    return np.asarray([[row[key] for key in FEATURES] for row in rows], dtype=np.float32)


def fit_rows(rows):
    """按换槽批次做树级均衡抽样后拟合隔离森林。

    每棵树先从全部换槽批次中无放回、等概率抽取至多 ``SAMPLE_LIMIT`` 个不同批次，
    再在每个中选批次内等概率抽一条控制条。这样洗 10 条的勤样批次不会以十倍权重
    进入同一棵树。
    """
    fit = feature_matrix(rows)
    if np.count_nonzero(np.ptp(fit, axis=0)) < 2:
        raise ValueError('历史拟合组至少需要两项读数有变化，请核对是否导入了重复或占位读数')
    if len(np.unique(fit, axis=0)) < 16:
        raise ValueError('历史拟合组至少需要 16 种不同的读数组合，请补充独立取样')

    batches = {}
    for index, row in enumerate(rows):
        batches.setdefault(row['change_id'], []).append(index)
    batch_ids = sorted(batches)
    batch_indices = [batches[change_id] for change_id in batch_ids]
    sample_size = min(SAMPLE_LIMIT, len(batch_indices))

    sampler = np.random.RandomState(FOREST_SEED)
    estimators = []
    estimator_features = []
    for tree_index in range(TREE_COUNT):
        chosen_batches = sampler.choice(len(batch_indices), size=sample_size, replace=False)
        chosen_rows = []
        for batch_number in chosen_batches:
            members = batch_indices[int(batch_number)]
            chosen_rows.append(members[int(sampler.randint(len(members)))])
        tree_x = fit[np.asarray(chosen_rows, dtype=int)]

        # 单树森林保证这棵 ExtraTree 只看见本轮“一批一条”的样本；所有树的
        # max_samples 均相同，后续可直接交回 scikit-learn 统一计算路径长度。
        tree_forest = IsolationForest(
            n_estimators=1,
            max_samples=sample_size,
            max_features=1.0,
            contamination='auto',
            random_state=FOREST_SEED + tree_index + 1,
            n_jobs=1,
        )
        tree_forest.fit(tree_x)
        estimators.append(tree_forest.estimators_[0])
        estimator_features.append(tree_forest.estimators_features_[0])

    forest = IsolationForest(
        n_estimators=1,
        max_samples=sample_size,
        max_features=1.0,
        contamination='auto',
        random_state=FOREST_SEED,
        n_jobs=1,
    )
    # 用一棵普通树完成 scikit-learn 的输入规格初始化，随后替换成 256 棵
    # 批次均衡树；评分公式只依赖 estimators_、max_samples_ 和路径长度属性。
    forest.fit(fit[:max(2, sample_size)])
    forest.n_estimators = TREE_COUNT
    forest.estimators_ = estimators
    forest.estimators_features_ = estimator_features
    forest.max_samples_ = sample_size
    forest._max_samples = sample_size
    forest._max_features = len(FEATURES)
    forest.offset_ = -0.5
    from sklearn.ensemble._iforest import _average_path_length

    forest._average_path_length_per_tree, forest._decision_path_lengths = zip(*[
        (
            _average_path_length(tree.tree_.n_node_samples),
            tree.tree_.compute_node_depths(),
        )
        for tree in forest.estimators_
    ])
    return forest


def score_groups(groups):
    forest = fit_rows(groups['reference_fit'])
    return {
        split: -forest.score_samples(feature_matrix(groups[split]))
        for split in ('reference_cal', 'shift')
    }
