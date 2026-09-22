import json, re, urllib.parse

har_path = r"c:\Users\Admin\Desktop\project\KHILOADFB.har"
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

dtsg_tokens = set()
lsd_tokens = set()
c_users = set()

for entry in har['log']['entries']:
    req = entry.get('request', {})
    headers = {h['name'].lower(): h['value'] for h in req.get('headers', [])}
    if 'cookie' in headers:
        c_m = re.findall(r'c_user=(\d+)', headers['cookie'])
        for c in c_m: c_users.add(c)
    
    pd = req.get('postData', {}).get('text', '')
    if pd:
        try:
            parsed = urllib.parse.parse_qs(pd)
            if 'fb_dtsg' in parsed: dtsg_tokens.add(parsed['fb_dtsg'][0])
            if 'lsd' in parsed: lsd_tokens.add(parsed['lsd'][0])
        except:
            pass

print("=== TOKENS FOUND IN KHILOADFB.HAR ===")
print("c_user IDs:", list(c_users))
print("LSD tokens:", list(lsd_tokens))
print("fb_dtsg sample:", [t[:15] + "..." for t in list(dtsg_tokens)])
