import sqlite3
from contextlib import contextmanager
from datetime import datetime


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    def _configure(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA busy_timeout=4000;")
        self.conn.commit()

    def _migrate(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA user_version;")
        ver = int(cur.fetchone()[0])

        if ver < 1:
            self._create_v1()
            cur.execute("PRAGMA user_version=1;")
            self.conn.commit()
            ver = 1

        if ver < 2:
            self._migrate_to_v2_hierarchy()
            cur.execute("PRAGMA user_version=2;")
            self.conn.commit()
            ver = 2

        if ver < 3:
            self._migrate_to_v3_custom_list_values()
            cur.execute("PRAGMA user_version=3;")
            self.conn.commit()
            ver = 3

    def _create_v1(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT    NOT NULL DEFAULT '',
                due_date    TEXT    NULL,              -- ISO date: YYYY-MM-DD
                last_update TEXT    NOT NULL,
                priority    INTEGER NOT NULL DEFAULT 3, -- 1..5
                status      TEXT    NOT NULL DEFAULT 'Todo',
                sort_order  INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_sort ON tasks(sort_order);

            CREATE TABLE IF NOT EXISTS custom_columns (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                col_type    TEXT    NOT NULL,           -- text|int|date|bool
                created_at  TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_custom_values (
                task_id     INTEGER NOT NULL,
                column_id   INTEGER NOT NULL,
                value       TEXT    NULL,
                PRIMARY KEY (task_id, column_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (column_id) REFERENCES custom_columns(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    def _migrate_to_v2_hierarchy(self):
        """
        Adds:
          - parent_id (self-referential FK, cascade delete)
          - is_collapsed (persist UI collapse)
          - per-parent sort_order usage (index)
        """
        cur = self.conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks';")
        if not cur.fetchone():
            # Fresh DB (shouldn't happen if v1 ran), just create v2
            self._create_tasks_v2_table()
            return

        # Create new table
        self._create_tasks_v2_table(temp_name="tasks_new")

        # Copy existing tasks (as top-level)
        cur.execute(
            """
            INSERT INTO tasks_new (id, description, due_date, last_update, priority, status, parent_id, sort_order, is_collapsed)
            SELECT id, description, due_date, last_update, priority, status, NULL, sort_order, 0
            FROM tasks;
            """
        )

        # Swap tables
        cur.execute("DROP TABLE tasks;")
        cur.execute("ALTER TABLE tasks_new RENAME TO tasks;")

        # Recreate indexes
        cur.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_parent_sort ON tasks(parent_id, sort_order);
            """
        )
        self.conn.commit()

    def _create_tasks_v2_table(self, temp_name: str = "tasks_new"):
        cur = self.conn.cursor()
        cur.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {temp_name} (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                description  TEXT    NOT NULL DEFAULT '',
                due_date     TEXT    NULL,               -- ISO date YYYY-MM-DD
                last_update  TEXT    NOT NULL,
                priority     INTEGER NOT NULL DEFAULT 3,  -- 1..5
                status       TEXT    NOT NULL DEFAULT 'Todo',
                parent_id    INTEGER NULL,
                sort_order   INTEGER NOT NULL,
                is_collapsed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (parent_id) REFERENCES {temp_name}(id) ON DELETE CASCADE
            );
            """
        )

    def _migrate_to_v3_custom_list_values(self):
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS custom_column_list_values (
                column_id   INTEGER NOT NULL,
                value       TEXT    NOT NULL,
                sort_order  INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (column_id, value),
                FOREIGN KEY (column_id) REFERENCES custom_columns(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_custom_column_list_values_col_sort
            ON custom_column_list_values(column_id, sort_order, value);
            """
        )

    @contextmanager
    def tx(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------- Custom columns ----------
    def fetch_custom_columns(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, col_type FROM custom_columns ORDER BY id;")
        cols = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT column_id, value
            FROM custom_column_list_values
            ORDER BY column_id, sort_order ASC, value ASC;
            """
        )
        list_rows = cur.fetchall()
        list_values_by_col = {}
        for r in list_rows:
            cid = int(r["column_id"])
            list_values_by_col.setdefault(cid, []).append(str(r["value"]))

        for c in cols:
            if str(c.get("col_type") or "") == "list":
                c["list_values"] = list_values_by_col.get(int(c["id"]), [])

        return cols

    def _normalize_list_values(self, list_values) -> list[str]:
        if not isinstance(list_values, list):
            return []
        out = []
        seen = set()
        for v in list_values:
            s = str(v).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    def _insert_list_values(self, cur, col_id: int, list_values: list[str]):
        for i, val in enumerate(list_values, start=1):
            cur.execute(
                """
                INSERT INTO custom_column_list_values(column_id, value, sort_order)
                VALUES(?, ?, ?)
                ON CONFLICT(column_id, value) DO NOTHING;
                """,
                (int(col_id), val, i),
            )

    def add_custom_column(self, name: str, col_type: str, list_values: list[str] | None = None) -> int:
        normalized = self._normalize_list_values(list_values)
        with self.tx():
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO custom_columns(name, col_type, created_at) VALUES(?, ?, ?);",
                (name.strip(), col_type, now_iso()),
            )
            col_id = int(cur.lastrowid)
            if col_type == "list" and normalized:
                self._insert_list_values(cur, col_id, normalized)
            return col_id

    def remove_custom_column(self, col_id: int):
        with self.tx():
            cur = self.conn.cursor()
            cur.execute("DELETE FROM custom_columns WHERE id=?;", (int(col_id),))

    def restore_custom_column(self, col: dict):
        list_values = self._normalize_list_values(col.get("list_values"))
        with self.tx():
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO custom_columns(id, name, col_type, created_at) VALUES(?, ?, ?, ?);",
                (int(col["id"]), col["name"], col["col_type"], col["created_at"]),
            )
            if str(col.get("col_type") or "") == "list" and list_values:
                self._insert_list_values(cur, int(col["id"]), list_values)

    def add_custom_column_list_value(self, col_id: int, value: str) -> bool:
        s = str(value).strip()
        if not s:
            return False
        with self.tx():
            cur = self.conn.cursor()
            cur.execute(
                "SELECT 1 FROM custom_column_list_values WHERE column_id=? AND value=?;",
                (int(col_id), s),
            )
            if cur.fetchone():
                return False

            cur.execute(
                "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM custom_column_list_values WHERE column_id=?;",
                (int(col_id),),
            )
            next_order = int(cur.fetchone()["next_order"])

            cur.execute(
                """
                INSERT INTO custom_column_list_values(column_id, value, sort_order)
                VALUES(?, ?, ?);
                """,
                (int(col_id), s, next_order),
            )
        return True

    # ---------- Tasks (hierarchy) ----------
    def fetch_tasks(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, description, due_date, last_update, priority, status,
                   parent_id, sort_order, is_collapsed
            FROM tasks
            ORDER BY COALESCE(parent_id, 0), sort_order ASC, id ASC;
            """
        )
        tasks = [dict(r) for r in cur.fetchall()]

        # Load custom values in one pass
        cur.execute(
            """
            SELECT task_id, column_id, value
            FROM task_custom_values;
            """
        )
        cv = cur.fetchall()
        values_by_task = {}
        for r in cv:
            values_by_task.setdefault(r["task_id"], {})[r["column_id"]] = r["value"]

        for t in tasks:
            t["custom"] = values_by_task.get(t["id"], {})
        return tasks

    def fetch_task_by_id(self, task_id: int) -> dict | None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, description, due_date, last_update, priority, status,
                   parent_id, sort_order, is_collapsed
            FROM tasks
            WHERE id=?;
            """,
            (int(task_id),),
        )
        r = cur.fetchone()
        if not r:
            return None
        task = dict(r)

        cur.execute(
            "SELECT column_id, value FROM task_custom_values WHERE task_id=?;",
            (int(task_id),),
        )
        task["custom"] = {int(x["column_id"]): x["value"] for x in cur.fetchall()}
        return task

    def next_sort_order(self, parent_id: int | None) -> int:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM tasks WHERE parent_id IS ?;",
            (parent_id,),
        )
        return int(cur.fetchone()[0])

    def insert_task(self, task: dict, keep_id: bool = False) -> int:
        """
        task keys:
          id(optional), description, due_date, last_update, priority, status,
          parent_id, sort_order, is_collapsed, custom{col_id:value}
        """
        with self.tx():
            cur = self.conn.cursor()

            if keep_id and task.get("id") is not None:
                cur.execute(
                    """
                    INSERT INTO tasks(id, description, due_date, last_update, priority, status,
                                      parent_id, sort_order, is_collapsed)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        task["id"], task["description"], task["due_date"], task["last_update"],
                        task["priority"], task["status"],
                        task.get("parent_id"), task["sort_order"], int(task.get("is_collapsed", 0))
                    ),
                )
                task_id = int(task["id"])
            else:
                cur.execute(
                    """
                    INSERT INTO tasks(description, due_date, last_update, priority, status,
                                      parent_id, sort_order, is_collapsed)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        task["description"], task["due_date"], task["last_update"],
                        task["priority"], task["status"],
                        task.get("parent_id"), task["sort_order"], int(task.get("is_collapsed", 0))
                    ),
                )
                task_id = int(cur.lastrowid)

            custom = task.get("custom") or {}
            for col_id, val in custom.items():
                cur.execute(
                    """
                    INSERT INTO task_custom_values(task_id, column_id, value)
                    VALUES(?, ?, ?)
                    ON CONFLICT(task_id, column_id) DO UPDATE SET value=excluded.value;
                    """,
                    (task_id, int(col_id), val),
                )

        return task_id

    def delete_task(self, task_id: int):
        with self.tx():
            cur = self.conn.cursor()
            cur.execute("DELETE FROM tasks WHERE id=?;", (int(task_id),))

    def update_task_field(self, task_id: int, field: str, value):
        if field not in {"description", "due_date", "priority", "status"}:
            raise ValueError("Invalid field")
        with self.tx():
            cur = self.conn.cursor()
            cur.execute(
                f"UPDATE tasks SET {field}=?, last_update=? WHERE id=?;",
                (value, now_iso(), int(task_id)),
            )

    def update_custom_value(self, task_id: int, col_id: int, value):
        with self.tx():
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO task_custom_values(task_id, column_id, value)
                VALUES(?, ?, ?)
                ON CONFLICT(task_id, column_id) DO UPDATE SET value=excluded.value;
                """,
                (int(task_id), int(col_id), value),
            )
            cur.execute("UPDATE tasks SET last_update=? WHERE id=?;", (now_iso(), int(task_id)))

    def set_task_collapsed(self, task_id: int, collapsed: bool):
        with self.tx():
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE tasks SET is_collapsed=?, last_update=? WHERE id=?;",
                (1 if collapsed else 0, now_iso(), int(task_id)),
            )

    def move_task(
        self,
        task_id: int,
        new_parent_id: int | None,
        old_parent_id: int | None,
        old_parent_order: list[int],
        new_parent_order: list[int],
    ):
        """
        Updates:
          - parent_id of moved node
          - sort_order of old parent siblings
          - sort_order of new parent siblings
        All in one transaction.
        """
        with self.tx():
            cur = self.conn.cursor()
            cur.execute("UPDATE tasks SET parent_id=? WHERE id=?;", (new_parent_id, int(task_id)))

            for i, tid in enumerate(old_parent_order, start=1):
                cur.execute("UPDATE tasks SET sort_order=? WHERE id=?;", (i, int(tid)))

            for i, tid in enumerate(new_parent_order, start=1):
                cur.execute("UPDATE tasks SET sort_order=? WHERE id=?;", (i, int(tid)))
