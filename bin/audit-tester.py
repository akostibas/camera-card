#!/usr/bin/env python3
"""Audit a ui-tester transcript: tool counts, and any URL other than a prototype page."""
import json, re, sys, collections
calls, bad = collections.Counter(), []
for line in open(sys.argv[1]):
    try: m = json.loads(line).get('message', {})
    except ValueError: continue
    for b in m.get('content', []) if isinstance(m.get('content'), list) else []:
        if b.get('type') != 'tool_use': continue
        name, inp = b['name'].split('__')[-1], b.get('input', {})
        calls[name + (':' + inp['action'] if 'action' in inp else '')] += 1
        url = inp.get('url')
        if url and not re.fullmatch(r'http://127\.0\.0\.1:8777/(alpha|bravo|charlie[23]?)\.html\?run=[\w-]+&seed=\d&task=\d', url):
            bad.append(url)
print(dict(calls))
print('OFF-LIMITS URLS:', bad or 'none')
