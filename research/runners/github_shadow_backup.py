"""Back up an explicitly named freeze to GitHub without exposing credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import urllib.error

REPO = 'harshil0014/stock-ranking-platform-checkpoint'


def credential():
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True, check=True)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    return fields['password']


def api(token, path, method='GET', value=None, data=None, content_type='application/json'):
    url = path if path.startswith('https://') else 'https://api.github.com/repos/' + REPO + path
    if not url.startswith(('https://api.github.com/', 'https://uploads.github.com/')):
        raise ValueError('Unexpected API destination')
    body = json.dumps(value).encode() if value is not None else data
    request = urllib.request.Request(url, data=body, method=method, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10', 'Content-Type': content_type, 'User-Agent': 'stock-ranking-shadow-backup'})
    try:
        with urllib.request.urlopen(request, timeout=1200) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'GitHub HTTP {error.code}: {error.read().decode()[:500]}') from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['status', 'publish', 'verify-release'])
    parser.add_argument('--tag')
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    token = credential()
    repo = api(token, '')
    if args.command == 'status':
        print(json.dumps({k: repo.get(k) for k in ['full_name', 'private', 'permissions', 'default_branch']}, indent=2))
        return
    if not repo.get('private'):
        raise ValueError('Backup archive contains local research inputs; private repository required')
    assets = sorted(p for p in args.assets.iterdir() if p.is_file())
    if not assets:
        raise ValueError('No backup assets')
    tag = api(token, '/git/ref/tags/' + args.tag)['object']
    if tag['type'] == 'tag':
        tag = api(token, '/git/tags/' + tag['sha'])['object']
    if tag['type'] != 'commit' or tag['sha'] != 'd4995807163bef1ec4b297179e6c54a59c71f390':
        raise ValueError('Remote freeze tag does not resolve to the original challenger')
    if args.command == 'verify-release':
        release = api(token, '/releases/tags/' + args.tag)
        if release['draft'] or not release.get('immutable'):
            raise ValueError('Published immutable release required')
        remote_assets = {a['name']: a for a in api(token, f"/releases/{release['id']}/assets?per_page=100")}
        verified = []
        for path in assets:
            expected = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
            item = remote_assets[path.name]
            if item.get('digest') != expected or item['size'] != path.stat().st_size:
                raise ValueError('Published asset mismatch: ' + path.name)
            verified.append({'name': path.name, 'size': item['size'], 'digest': expected, 'url': item['browser_download_url']})
        receipt = {'repository': REPO, 'private': True, 'tag': args.tag, 'tag_commit': tag['sha'], 'release_url': release['html_url'], 'release_id': release['id'], 'immutable': True, 'assets': verified}
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(json.dumps(receipt, indent=2))
        return
    api(token, '/immutable-releases', 'PUT')
    enabled = api(token, '/immutable-releases')
    if not enabled.get('enabled'):
        raise ValueError('Release immutability not enabled')
    releases = api(token, '/releases?per_page=100')
    matches = [r for r in releases if r['tag_name'] == args.tag]
    release = matches[0] if matches else api(token, '/releases', 'POST', {'tag_name': args.tag, 'name': args.tag, 'draft': True, 'body': 'Immutable personalized challenger d499580: 67% Goal + 33% LightGBM LambdaRank. Research only; production unchanged. Attached archives include the frozen predictions, model, lineage, shadow engine and checksummed reproduction inputs.', 'make_latest': 'false'})
    if release.get('immutable'):
        raise ValueError('Release already immutable; verify existing receipt instead of mutating')
    if not release['draft']:
        raise ValueError('Refuse to modify a published release')
    existing = {a['name']: a for a in api(token, f"/releases/{release['id']}/assets?per_page=100")}
    verified = []
    for path in assets:
        expected = 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()
        if path.name in existing:
            item = existing[path.name]
            # GitHub leaves a zero-byte starter asset when a connection is
            # interrupted. Only remove that incomplete asset on this verified
            # draft release; never replace a completed or published asset.
            if item.get('state') == 'starter' and not item.get('digest'):
                api(token, f"/releases/assets/{item['id']}", 'DELETE')
                item = api(token, release['upload_url'].split('{')[0] + '?name=' + path.name, 'POST', data=path.read_bytes(), content_type='application/octet-stream')
        else:
            item = api(token, release['upload_url'].split('{')[0] + '?name=' + path.name, 'POST', data=path.read_bytes(), content_type='application/octet-stream')
        if item.get('digest') != expected or item['size'] != path.stat().st_size:
            raise ValueError('Uploaded asset digest/size mismatch: ' + path.name)
        verified.append({'name': path.name, 'size': item['size'], 'digest': expected, 'url': item['browser_download_url']})
        print('Verified uploaded asset: ' + path.name, flush=True)
    published = api(token, f"/releases/{release['id']}", 'PATCH', {'draft': False, 'make_latest': 'false'})
    published = api(token, f"/releases/{release['id']}")
    if not published.get('immutable'):
        raise ValueError('GitHub did not confirm immutable release')
    final_assets = {a['name']: a for a in api(token, f"/releases/{release['id']}/assets?per_page=100")}
    for item in verified:
        remote = final_assets[item['name']]
        if remote.get('digest') != item['digest'] or remote['size'] != item['size']:
            raise ValueError('Published asset verification failed')
        item['url'] = remote['browser_download_url']
    receipt = {'repository': REPO, 'private': True, 'tag': args.tag, 'tag_commit': tag['sha'], 'release_url': published['html_url'], 'release_id': published['id'], 'immutable': published['immutable'], 'assets': verified}
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
