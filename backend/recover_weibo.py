import sqlite3
import json
import glob
import os
from datetime import datetime

conn = sqlite3.connect('tasks.db')
cursor = conn.cursor()

files = glob.glob('checkpoints/weibo_*.json')
restored = 0

for f in files:
    task_id = os.path.basename(f).replace('weibo_', '').replace('.json', '')
    
    cursor.execute("SELECT task_id FROM tasks WHERE task_id = ?", (task_id,))
    if cursor.fetchone():
        continue
        
    with open(f, 'r') as fp:
        try:
            data = json.load(fp)
        except: continue
        
    keyword = data.get('keyword', 'Recovered')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    display_kw = keyword
    if start_date and end_date and "since:" not in keyword:
        display_kw = f"{keyword} since:{start_date} until:{end_date}"
        
    posts = data.get('posts', [])
    result_count = len(posts)
    now = datetime.now().isoformat()
    
    try:
        cursor.execute("""
            INSERT INTO tasks (
                task_id, status, keyword, product, max_count, result_count, 
                current_page, created_at, finished_at, error, risk_state, 
                quality_state, runtime_metrics_json, time_coverage_json,
                last_event_at, resumed, fetch_replies, max_replies_per_tweet,
                reply_depth, crawl_strategy, replies_fetched, crawl_phase,
                task_kind, preview_json, platform, start_date, end_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, "done", display_kw, "top", result_count or 100, result_count,
            1, now, now, None, "none",
            "complete", "{}", "{}",
            now, 1, 0, 0,
            0, "latest", 0, "已从备份恢复",
            "search", "[]", "weibo", start_date, end_date
        ))
        
        cursor.execute("""
            INSERT INTO task_results (task_id, tweets_json, updated_at)
            VALUES (?, ?, ?)
        """, (task_id, json.dumps(posts, ensure_ascii=False), now))
        
    except Exception as e:
        print(f"Error restoring {task_id}: {e}")
        continue
        
    restored += 1
    print(f"Restored: {display_kw} ({result_count} items)")

conn.commit()
conn.close()
print(f"Total restored: {restored}")
