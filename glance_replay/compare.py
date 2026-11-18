"""Offline comparison of declared profiles in one hypothetical app model."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
from . import core

SCOPE = ('Declared hypothetical profiles in the same deterministic app model. '
         'No device, SDK, speech recognition, model, network, energy measurement '
         'or real permission guarantee. Different outcomes do not rank devices.')
FILES = {'source.json', 'comparison.json', 'comparison.txt'}


def load(raw):
    value = core.parse(raw)
    core.fields(value, ['schema', 'replay_schema', 'initial', 'events', 'configurations'])
    core.integer(value['schema'], 1, 1)
    core.integer(value['replay_schema'], 1, 2)
    configs = value['configurations']
    if not isinstance(configs, list) or not 2 <= len(configs) <= 8:
        raise core.Invalid('Expected 2..8 hypothetical configurations.')
    ids = set()
    for config in configs:
        core.fields(config, ['id', 'profile', 'assertions'])
        core.identifier(config['id'])
        if config['id'] in ids:
            raise core.Invalid('Duplicate configuration ID.')
        ids.add(config['id'])
        # Validation is exactly the existing schema 1 or 2 validator.
        core.load(core.canonical(_scenario(value, config)))
    return value


def _scenario(value, config):
    return {'schema': value['replay_schema'], 'profile': config['profile'],
            'initial': value['initial'], 'events': value['events'],
            'assertions': config['assertions']}


def assertion_status(checks):
    if not checks:
        return 'no_assertions'
    return 'pass' if all(check['passed'] for check in checks) else 'fail'


def analyze(raw):
    value = load(raw)
    runs = [{'id': config['id'], 'replay': core.replay(core.canonical(_scenario(value, config)))}
            for config in value['configurations']]
    events = []
    for index, event in enumerate(value['events']):
        states = [(run['id'], run['replay']['trace'][index]) for run in runs]
        different = {}
        for key in sorted(states[0][1]):
            if len({core.canonical(state[key]) for _, state in states}) > 1:
                different[key] = {name: state[key] for name, state in states}
        outcomes = []
        for run in runs:
            state = run['replay']['trace'][index]
            checks = [check for check in run['replay']['assertions'] if check['after_event'] == index]
            outcomes.append({'configuration': run['id'], 'result': state['result'],
                'rejection_reason': state['result'] if state['result'].startswith('denied_') else None,
                'assertion_status': assertion_status(checks), 'assertion_count': len(checks)})
        events.append({'after_event': index, 'event': event, 'different_fields': different,
                       'outcomes': outcomes})
    pairs = []
    for left, right in itertools.combinations(runs, 2):
        indices = [i for i, (a, b) in enumerate(zip(left['replay']['trace'], right['replay']['trace']))
                   if core.canonical(a) != core.canonical(b)]
        pairs.append({'left': left['id'], 'right': right['id'],
            'profiles_identical': core.canonical(left['replay']['profile']) == core.canonical(right['replay']['profile']),
            'trace_identical': not indices, 'different_event_indices': indices,
            'first_divergence': indices[0] if indices else None})
    first = next((item['after_event'] for item in events if item['different_fields']), None)
    statuses = {run['id']: run['replay']['status'] for run in runs}
    return {'schema': 1, 'algorithm': 'glance-profile-comparison-v1',
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'replay_schema': value['replay_schema'],
        'policy': runs[0]['replay']['policy'], 'configuration_order': [run['id'] for run in runs],
        'assertion_statuses': statuses, 'all_assertions_pass': all(s == 'pass' for s in statuses.values()),
        'first_divergence': first, 'pairs': pairs, 'events': events, 'runs': runs, 'scope': SCOPE}


def text_report(report):
    lines = ['GLANCE REPLAY / HYPOTHETICAL PROFILE COMPARISON', SCOPE,
             'First observable trace divergence: ' + str(report['first_divergence']),
             'All configurations have passing assertions: ' + str(report['all_assertions_pass']),
             'No assertions is not pass. Identical failures are not success.', '']
    for name, status in report['assertion_statuses'].items():
        lines.append(name + ': ' + status)
    for pair in report['pairs']:
        lines.append('Pair ' + pair['left'] + ' / ' + pair['right'] + ': first divergence=' + str(pair['first_divergence'])
                     + '; profiles identical=' + str(pair['profiles_identical']))
    for item in report['events']:
        lines.extend(['', 'Event ' + str(item['after_event']) + ': ' + json.dumps(item['event'], ensure_ascii=True, sort_keys=True)])
        for outcome in item['outcomes']:
            lines.append('  ' + outcome['configuration'] + ': result=' + outcome['result']
                         + '; rejection=' + str(outcome['rejection_reason'])
                         + '; assertions=' + outcome['assertion_status'])
        if not item['different_fields']:
            lines.append('  No observable trace difference at this event.')
        for field, values in item['different_fields'].items():
            lines.append('  ' + field + ': ' + json.dumps(values, ensure_ascii=True, sort_keys=True))
    return ('\n'.join(lines) + '\n').encode('utf8')


def outputs(raw):
    report = analyze(raw)
    files = {'source.json': raw, 'comparison.json': core.canonical(report), 'comparison.txt': text_report(report)}
    if any(len(content) > core.OUTPUT_LIMIT for content in files.values()):
        raise core.Invalid('Comparison exceeds output bounds.')
    return report, files


def build(source, out):
    report, files = outputs(core.read(source))
    destination = Path(out)
    destination.mkdir(mode=0o700, exist_ok=False)
    for name, content in files.items():
        fd = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
    return report


def verify(folder):
    root = Path(folder)
    if root.is_symlink() or not root.is_dir() or {p.name for p in root.iterdir()} != FILES:
        raise core.Invalid('Unexpected comparison bundle structure.')
    report, expected = outputs(core.read(root / 'source.json'))
    for name, content in expected.items():
        if core.read(root / name, core.INPUT_LIMIT if name == 'source.json' else core.OUTPUT_LIMIT) != content:
            raise core.Invalid('Comparison differs from input recomputation.')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    make = commands.add_parser('build'); make.add_argument('source'); make.add_argument('--out', required=True)
    check = commands.add_parser('verify'); check.add_argument('folder')
    for command in (make, check):
        command.add_argument('--require-all-pass', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = build(args.source, args.out) if args.command == 'build' else verify(args.folder)
        print(json.dumps({'consistent': True, 'first_divergence': report['first_divergence'],
            'assertion_statuses': report['assertion_statuses'], 'all_assertions_pass': report['all_assertions_pass'], 'scope': SCOPE}, sort_keys=True))
        return 3 if args.require_all_pass and not report['all_assertions_pass'] else 0
    except (core.Invalid, OSError, ValueError, RecursionError):
        print('Cannot compare bounded hypothetical profiles: invalid input, inconsistent evidence or filesystem failure. Input text is not echoed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
