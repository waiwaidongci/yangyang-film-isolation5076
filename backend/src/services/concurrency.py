import threading


# SQLite 不支持 SELECT ... FOR UPDATE 行锁；演示/验收通常为单进程 TestClient 或
# uvicorn worker。用进程内临界区把“补录重算”和“签核核对”串行化。Postgres 下
# 仍同时使用 FOR UPDATE 与条件 UPDATE，形成双保险。
workflow_lock = threading.RLock()
