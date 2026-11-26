from sqlalchemy import inspect, text

from src.config.database import Base, engine
from src.models import account, dataset, review, run  # noqa: F401


# SQLite 的 create_all 不会给旧表补列；演示/验收库可能保留具名卷。
COLUMN_PATCHES = {
    'datasets': {
        'version': 'INTEGER NOT NULL DEFAULT 1',
        'updated_at': 'VARCHAR(32)',
    },
    'analysis_runs': {
        'source_version': 'INTEGER NOT NULL DEFAULT 1',
        'basis_digest': 'VARCHAR(64)',
        'is_current': 'BOOLEAN NOT NULL DEFAULT 1',
        'superseded_by_id': 'INTEGER REFERENCES analysis_runs(id)',
    },
    'reviews': {
        'source_version': 'INTEGER',
        'basis_digest': 'VARCHAR(64)',
        'basis': 'JSON',
    },
}


def bootstrap():
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in COLUMN_PATCHES.items():
            if table not in existing_tables:
                continue
            present = {column['name'] for column in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in present:
                    connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
