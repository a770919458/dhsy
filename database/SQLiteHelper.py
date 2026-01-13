import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional, Sequence, Any


class SQLiteHelper:
    """
    轻量级 SQLite 工具类：
        - 自动建库/建表
        - 上下文管理，所有写操作默认自动提交
        - 提供常用的增删改查封装
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 可选，返回 dict-like 行
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        """执行任意 SQL，不返回结果"""
        with self._connect() as conn:
            conn.execute(sql, params)

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> None:
        with self._connect() as conn:
            conn.executemany(sql, seq_of_params)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """返回多行结果（Row 可当 dict 用）"""
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchone()




if __name__ == "__main__":
    helper = SQLiteHelper("data/game_data.db")
