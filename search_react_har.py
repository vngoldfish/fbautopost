import json, urllib.parse, sys

har_path = r"c:\Users\Admin\Desktop\project\loitestcamxuc.har"
sys.stdout.reconfigure(encoding='utf-8')
print(f"=== Searching React Entries in: {har_path} ===")

with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

entries = har['log']['entries']
react_entries = []

for idx, entry in enumerate(entries):
    req = entry.get('request', {})
    res = entry.get('response', {})
    url = req.get('url', '')
    post_data = req.get('postData', {}).get('text', '')
    
    if 'react' in post_data.lower() or 'feedback_react' in post_data.lower() or 'like' in post_data.lower():
        parsed = urllib.parse.parse_qs(post_data)
        name = parsed.get('fb_api_req_friendly_name', [''])[0]
        doc_id = parsed.get('doc_id', [''])[0]
        variables = parsed.get('variables', [''])[0]
        react_entries.append((idx+1, name, doc_id, variables))

print(f"Found {len(react_entries)} matching entries:\n")
for e in react_entries:
    print(f"Entry [{e[0]}]: Name={e[1]} | doc_id={e[2]}")
    print(f"   Vars: {e[3][:300]}\n")
