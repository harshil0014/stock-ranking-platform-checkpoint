"""Read-only public repository snapshots for the literature review; never executes fetched code."""
import concurrent.futures
import hashlib
import json
import pathlib
import urllib.request

OUT = pathlib.Path(__file__).resolve().parents[2] / 'research' / 'literature' / '20261017'
REPOS = ['microsoft/qlib', 'SJTU-DMTai/MASTER', 'SJTU-DMTai/DoubleAdapt',
         'Wentao-Xu/HIST', 'OpenSourceAP/CrossSection', 'rejinreeza/trading_tool',
         'ninad164/auto-portfolio-management', 'raogaurav17/Nifty-Quant',
         'shiyu-coder/Kronos', 'microsoft/RD-Agent']

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'LiteratureReview-readonly'})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()

def snapshot(repo):
    result = {'repo': repo, 'review_date': '2026-10-17', 'files': []}
    try:
        meta = json.loads(get('https://api.github.com/repos/' + repo))
        commit = json.loads(get('https://api.github.com/repos/' + repo + '/commits/' + meta['default_branch']))
        result.update(commit=commit['sha'], license=(meta.get('license') or {}).get('spdx_id'), archived=meta['archived'])
        tree = json.loads(get('https://api.github.com/repos/' + repo + '/git/trees/' + commit['sha'] + '?recursive=1'))
        folder = OUT / repo.replace('/', '__')
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'tree.json').write_text(json.dumps(tree, indent=2), encoding='utf-8')
        paths = [x['path'] for x in tree['tree'] if x['type'] == 'blob']
        wanted = [p for p in paths if p.lower() in ['readme.md', 'license', 'license.txt', 'license.md']]
        for p in wanted:
            url = 'https://raw.githubusercontent.com/' + repo + '/' + commit['sha'] + '/' + p
            data = get(url)
            (folder / p).write_bytes(data)
            result['files'].append({'path': p, 'url': url, 'sha256': hashlib.sha256(data).hexdigest()})
    except Exception as e:
        result['error'] = str(e)
    return result

if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(snapshot, REPOS))
    (OUT / 'repository_manifest.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    for r in results:
        print(r['repo'], r.get('commit', '')[:12], r.get('license'), r.get('error', 'OK'))
