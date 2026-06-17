#!/usr/bin/env python3
"""Audit repo for Simplified Chinese characters."""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIMPLIFIED_CHARS = '设数据导账户买卖仓损标巩'
EXCLUDE_DIRS = {'.git','node_modules','dist','build','coverage','__pycache__','.venv','venv','.cache','.local-artifacts-recovery','.omo','.runtime-validation','.gitnexus','.serena','logs','data','reports','cache','playwright-report','test-results'}
EXCLUDE_FILES = {'docs/README_CN.md','scripts/audit_zh_tw_text.py','tests/test_language_zh_tw_support.py','tests/test_route_b_zh_tw_localization.py','tests/test_tw_market_review_rendering.py'}
hits = 0
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
    for f in files:
        if not f.endswith(('.ts','.tsx','.py','.md','.json','.yml','.yaml','.txt','.sh','.ps1')): continue
        fp = os.path.join(root, f)
        rel = os.path.relpath(fp, ROOT)
        if rel in EXCLUDE_FILES: continue
        try:
            with open(fp, encoding='utf-8') as fh: content = fh.read()
        except: continue
        for ch in SIMPLIFIED_CHARS:
            if ch in content:
                print(f"  ❌ {rel}: char '{ch}'")
                hits += 1; break
if hits: print(f"\n❌ {hits} files with Simplified chars"); sys.exit(1)
else: print("\n✅ No Simplified-only characters found")
