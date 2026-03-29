import json
import glob
keywords = []
for f in glob.glob("checkpoints/weibo_*.json"):
    try:
        with open(f, 'r') as fp:
            d = json.load(fp)
            keywords.append(d.get('keyword', 'Unknown'))
    except: pass
for k in sorted(set(keywords)):
    print(k)
