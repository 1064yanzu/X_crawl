import sqlite3
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api.services.task_db import delete_task, _get_conn
tid = '155d5475-b293-4f50-9e1c-a3682a08276a'
with _get_conn() as conn:
    print(conn.execute("SELECT count(*) FROM tasks WHERE task_id=?", (tid,)).fetchone())
delete_task(tid)
with _get_conn() as conn:
    print(conn.execute("SELECT count(*) FROM tasks WHERE task_id=?", (tid,)).fetchone())
