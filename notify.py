"""MoDi Instagram：できた画像のURLを、スプレッドシートの下書きに書き戻す"""
import json, os
import requests

GAS_URL = os.environ['GAS_URL']
GAS_TOKEN = os.environ['GAS_TOKEN']
REPO = os.environ['GITHUB_REPOSITORY']
BRANCH = os.environ.get('GITHUB_REF_NAME', 'main')

with open('manifest.json') as f:
    manifest = json.load(f)
for m in manifest:
    urls = ['https://raw.githubusercontent.com/{}/{}/{}'.format(REPO, BRANCH, p) for p in m['files']]
    r = requests.post(GAS_URL, data=json.dumps({'token': GAS_TOKEN, 'row': m['row'], 'images': urls}), timeout=60)
    print('書き戻し：', m['row'], r.status_code)
