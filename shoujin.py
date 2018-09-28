# Python Version: 3.x
# -*- coding: utf-8 -*-
import datetime
import json
import pathlib
import random
import requests  # https://pypi.python.org/pypi/requests
import time

def requests_get_json(url):
    print('[*] GET', url)
    delay = random.random() * 2 + 1
    time.sleep(delay)
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.json()

def read_cache(path):
    if path is None:
        return None
    assert path.suffix == '.json'
    if path.exists():
        print('[*] read cache file:', path)
        with path.open() as fh:
            return json.loads(fh.read())
    else:
        return None

def write_cache(path, data):
    if path is None:
        return None
    assert path.suffix == '.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    print('[*] write cache file:', path)
    with path.open('w') as fh:
        fh.write(json.dumps(data))

class AtCoderShoujin(object):

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir
        self.contests = self._get_info_contests()
        self.problems = self._get_info_merged_problems()

    def _get_info_contests(self):
        url = 'http://kenkoooo.com/atcoder/atcoder-api/info/contests'
        data = requests_get_json(url)
        f = {}
        for row in data:
            f[row['id']] = row
        return f

    def _get_info_merged_problems(self):
        url = 'http://kenkoooo.com/atcoder/atcoder-api/info/merged-problems'
        data = requests_get_json(url)
        f = {}
        for row in data:
            f[row['id']] = row
        return f

    def _get_results_pair(self, user_id):
        # read cache
        cache_path = pathlib.Path(self.cache_dir) / 'atcoder' / (user_id + '.json')
        old_data = read_cache(cache_path) or []

        # use the API
        url = 'http://kenkoooo.com/atcoder/atcoder-api/results?user=' + user_id
        data = requests_get_json(url)

        # write cache
        write_cache(cache_path, data)

        return { 'new': data, 'old': old_data }

    def __call__(self, user_id):  #=> [ { 'title': str, 'url': str, 'score': str (optional) } ]
        results = self._get_results_pair(user_id)
        delta = {}

        # add new problems
        for submission in results['new']:
            if submission['result'] == 'AC':
                problem_id = submission['problem_id']
                contest_id = submission['contest_id']
                delta[problem_id] = {
                    'problem_id': problem_id,
                    'contest_id': contest_id,
                    'title': self.contests[contest_id]['title'] + ' ' + self.problems[problem_id]['title'],
                    'url': 'https://beta.atcoder.jp/contests/{}/tasks/{}'.format(contest_id, problem_id),
                }
                point = self.problems[problem_id].get('point')
                if point is not None:
                    delta[problem_id]['score'] = point

        # remove old problems
        for submission in results['old']:
            if submission['result'] == 'AC':
                if submission['problem_id'] in delta:
                    del delta[submission['problem_id']]

        delta = list(delta.values())
        delta.sort(key=lambda problem: problem['problem_id'])
        return delta


class CodeforcesShoujin(object):

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir
        self.contests = {}
        self.contests.update(self._get_contests())
        self.contests.update(self._get_contests(gym=True))

    def _get_contests(self, gym=False):
        url = 'http://codeforces.com/api/contest.list'
        if gym:
            url += '?gym=true'
        data = requests_get_json(url)
        assert data['status'] == 'OK'
        return { row['id']: row for row in data['result'] }

    def _get_results_pair(self, user_id):
        # read cache
        cache_path = pathlib.Path(self.cache_dir) / 'codeforces' / (user_id + '.json')
        old_data = read_cache(cache_path) or { 'result': [] }

        # use the API
        url = 'http://codeforces.com/api/user.status?handle=' + user_id
        data = requests_get_json(url)
        assert data['status'] == 'OK'

        # write cache
        write_cache(cache_path, data)

        return { 'new': data, 'old': old_data }

    def __call__(self, user_id):
        results = self._get_results_pair(user_id)
        delta = {}

        # add new problems
        for submission in results['new']['result']:
            if submission['verdict'] != 'OK':
                continue
            contest_id = submission['contestId']
            problem = submission['problem']
            problem_id = ( contest_id, problem['index'] )
            print(problem)
            delta[problem_id] = {
                'problem_id': problem_id,
                'title': self.contests[contest_id]['name'] + ': ' + problem['name'],
                'url': 'http://codeforces.com/contest/{}/problem/{}'.format(contest_id, problem['index']),
            }
            if 'points' in problem:
                delta[problem_id]['score'] = str(problem['points'])

        # remove old problems
        for submission in results['old']['result']:
            if submission['verdict'] != 'OK':
                continue
            problem_id = ( submission['contestId'], submission['problem']['index'] )
            if problem_id in delta:
                del delta[problem_id]

        delta = list(delta.values())
        delta.sort(key=lambda problem: problem['problem_id'])
        return delta


def make_data(users, cache_dir=None):
    services = {
        'atcoder': AtCoderShoujin(cache_dir=cache_dir),
        'codeforces': CodeforcesShoujin(cache_dir=cache_dir),
    }

    # gather data
    data = []
    for user_name, user in users.items():
        problems = []
        for service_name, user_id in user.items():
            problems += services[service_name](user_id)

        if not problems:
            continue

        if len(problems) > 30:
            text = ''
        else:
            texts = []
            texts += [ '_{}_ solved *{}* problems!'.format(user_name, len(problems)) ]
            for problem in problems:
                words = []
                words += [ problem['title'] ]
                if 'score' in problem:
                    words += [ '({} pts)'.format(problem['score']) ]
                words += [ problem['url'] ]
                texts += [ ' '.join(words) ]
            text = '\n'.join(texts)

        data += [ {
            'name': user_name,
            'problems': problems,
            'text': text,
        } ]

    # sort and concat
    data.sort(key=lambda row: len(row['problems']), reverse=True)
    text = '\n\n'.join([ row['text'] for row in data ])
    return text


appname = 'shoujin-slack-notifier'
default_config = {
    'users': {
        'kimiyuki': { 'atcoder': 'kimiyuki', 'codeforces': 'kimiyuki' },
        'tourist': { 'atcoder': 'tourist', 'codeforces': 'tourist' },
    },
    'webhook-url': 'https://hooks.slack.com/services/?????????/?????????/????????????????????????',
    'cache-dir': str(pathlib.Path('~/.cache/{}'.format(appname)).expanduser()),
}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('users', nargs='*')
    parser.add_argument('--webhook-url')
    parser.add_argument('--config-file', type=pathlib.Path, default=pathlib.Path('~/.config/{}/config.json'.format(appname)).expanduser())
    parser.add_argument('--cache-dir')
    parser.add_argument('--no-post', action='store_true')
    args = parser.parse_args()

    # load the config
    if not args.config_file.exists():
        print('[*] write config file:', args.config_file)
        args.config_file.parent.mkdir(parents=True, exist_ok=True)
        with args.config_file.open('w') as fh:
            fh.write(json.dumps(default_config))
    print('[*] read config file:', args.config_file)
    with args.config_file.open() as fh:
        args.config = json.loads(fh.read())

    # load default values
    if args.webhook_url is None:
        args.webhook_url = args.config['webhook-url']
    if len(args.users) == 0:
        args.users = args.config['users']
    if args.cache_dir is None:
        args.cache_dir = args.config['cache-dir']

    # print timestamp
    print('[*]', datetime.datetime.now())

    # make data
    text = make_data(args.users, cache_dir=args.cache_dir)

    # post data
    if not text:
        print('[*] nothing to notify...')
    else:
        print('[*] payload:')
        print(text)
        if not args.no_post:
            print('[*] POST', args.webhook_url)
            resp = requests.post(args.webhook_url, data=json.dumps({ 'text': text }))
            resp.raise_for_status()


if __name__ == '__main__':
    main()
