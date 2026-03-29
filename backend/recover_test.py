import os
import glob
print(glob.glob('checkpoints/weibo_*.json'))
import sqlite3
c = sqlite3.connect('tasks.db').cursor()
for f in glob.glob('checkpoints/weibo_*.json'):
    tid = os.path.basename(f).replace('weibo_', '').replace('.json', '')
    print(f"Checking {tid}")
    c.execute("SELECT task_id FROM tasks WHERE task_id=?", (tid,))
    row = c.fetchone()
    print("Found:", bool(row))
