"""Declared synthetic configurations, no browser or hardware execution."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from glance_replay import core, compare

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    source = json.loads((ROOT/'examples/platform-day.json').read_bytes())
    profile = source['profile']
    return {'schema': 1, 'replay_schema': 2,
        'initial': {'connected': True, 'worn': True,
                    'permissions': ['notifications', 'camera', 'microphone'],
                    'battery_percent': 80, 'phone_app': 'foreground', 'network': 'online'},
        'events': [{'at_ms': 0, 'type': 'wait'}],
        'configurations': [{'id': 'Left', 'profile': copy.deepcopy(profile), 'assertions': []},
                           {'id': 'Right', 'profile': copy.deepcopy(profile), 'assertions': []}]}


def run(value):
    return compare.analyze(core.canonical(value))


def notify(name, at=0):
    return {'at_ms': at, 'type': 'notify', 'id': name, 'text': 'Synthetic reminder',
            'priority': 1, 'ttl_ms': 1000, 'origin': 'local'}


class ModelComparison(unittest.TestCase):
    def test_identical_profiles_no_assertions_is_not_pass(self):
        report = run(fixture())
        self.assertIsNone(report['first_divergence'])
        self.assertTrue(report['pairs'][0]['profiles_identical'])
        self.assertTrue(report['pairs'][0]['trace_identical'])
        self.assertEqual(report['assertion_statuses'], {'Left': 'no_assertions', 'Right': 'no_assertions'})
        self.assertFalse(report['all_assertions_pass'])
    def test_offline_voice_independent_expectations_both_pass(self):
        value = fixture(); value['initial']['network'] = 'offline'
        value['events'] = [{'at_ms': 0, 'type': 'voice', 'command': 'next'}]
        for config, capability, expected in zip(value['configurations'], [False, True], ['denied_network', 'no_notification']):
            config['profile']['capabilities']['offline_voice'] = capability
            config['assertions'] = [{'after_event': 0, 'expect': {'result': expected}}]
        report = run(value)
        self.assertTrue(report['all_assertions_pass']); self.assertEqual(report['first_divergence'], 0)
        self.assertEqual(report['events'][0]['different_fields']['result'], {'Left': 'denied_network', 'Right': 'no_notification'})
        self.assertEqual(report['events'][0]['outcomes'][0]['rejection_reason'], 'denied_network')
        self.assertIsNone(report['events'][0]['outcomes'][1]['rejection_reason'])
    def test_assertion_fail_no_assertion_and_same_trace_not_conflated(self):
        value = fixture(); value['configurations'][0]['assertions'] = [{'after_event': 0, 'expect': {'result': 'connected'}}]
        report = run(value)
        self.assertEqual(report['assertion_statuses'], {'Left': 'fail', 'Right': 'no_assertions'})
        self.assertIsNone(report['first_divergence']); self.assertFalse(report['all_assertions_pass'])
    def test_background_queue_difference_starts_at_transition(self):
        value = fixture(); value['events'] = [notify('one'), {'at_ms': 1, 'type': 'phone_app', 'state': 'background'}, notify('two',2)]
        for config, flag in zip(value['configurations'], [False, True]):
            config['profile']['capabilities']['background_companion'] = flag
        report = run(value)
        self.assertEqual(report['first_divergence'], 1)
        self.assertEqual(report['events'][1]['different_fields']['queue'], {'Left': [], 'Right': ['one']})
        self.assertEqual(report['pairs'][0]['different_event_indices'], [1,2])
    def test_camera_capability_and_shared_permission_gates(self):
        value = fixture(); value['initial']['permissions'] = []
        value['events'] = [{'at_ms':0,'type':'capture','resource':'camera'}, {'at_ms':1,'type':'grant','permission':'camera'}, {'at_ms':2,'type':'capture','resource':'camera'}]
        value['configurations'][0]['profile']['capabilities']['camera'] = False
        value['configurations'][1]['profile']['capabilities']['camera'] = True
        report = run(value)
        self.assertEqual([x['result'] for x in report['events'][0]['outcomes']], ['denied_unsupported_resource','denied_permission'])
        self.assertEqual([x['result'] for x in report['events'][2]['outcomes']], ['denied_unsupported_resource','simulated_capture_allowed'])
    def test_queue_capacity_and_grid_are_observable_not_device_ranking(self):
        value = fixture(); value['events'] = [notify('one'),notify('two',1)]
        value['configurations'][0]['profile'].update(queue_limit=1,columns=4,rows=1)
        value['configurations'][1]['profile'].update(queue_limit=2,columns=20,rows=2)
        report = run(value)
        self.assertIn('screen',report['events'][0]['different_fields'])
        self.assertEqual(report['events'][1]['outcomes'][0]['result'],'dropped_capacity')
        self.assertIsNone(report['events'][1]['outcomes'][0]['rejection_reason'])
    def test_order_and_equal_timestamps_preserved(self):
        value=fixture();value['events']=[notify('one'),{'at_ms':0,'type':'dismiss'},{'at_ms':0,'type':'wait'}]
        report=run(value)
        self.assertEqual([x['event'] for x in report['events']],value['events'])
        self.assertEqual([x['after_event'] for x in report['events']],[0,1,2])
        value['events'][0],value['events'][1]=value['events'][1],value['events'][0]
        self.assertEqual(run(value)['runs'][0]['replay']['trace'][-1]['queue'],['one'])
    def test_configuration_order_changes_presentation_not_labeled_results(self):
        value=fixture();value['configurations'][0]['profile']['capabilities']['camera']=False
        value['events']=[{'at_ms':0,'type':'capture','resource':'camera'}]
        left=run(value);value['configurations'].reverse();right=run(value)
        self.assertEqual({r['id']:r['replay'] for r in left['runs']},{r['id']:r['replay'] for r in right['runs']})
        self.assertEqual(right['configuration_order'],['Right','Left'])
    def test_schema1_supported_without_platform_fields(self):
        old=json.loads((ROOT/'examples/notification-day.json').read_bytes())
        value={'schema':1,'replay_schema':1,'initial':old['initial'],'events':old['events'],'configurations':[{'id':x,'profile':old['profile'],'assertions':old['assertions']} for x in ['A','B']]}
        report=run(value);self.assertEqual(report['runs'][0]['replay'],core.replay(core.canonical(old)))
        self.assertTrue(report['all_assertions_pass']);self.assertIsNone(report['first_divergence'])
    def test_two_to_eight_and_all_pair_first_divergences(self):
        value=fixture();value['configurations']=[{**copy.deepcopy(value['configurations'][0]),'id':'p'+str(i)} for i in range(8)]
        report=run(value);self.assertEqual(len(report['pairs']),28)
        self.assertTrue(all(p['first_divergence'] is None for p in report['pairs']))
        for n in (0,1,9):
            bad=copy.deepcopy(value);bad['configurations']=(bad['configurations']*2)[:n]
            with self.assertRaises(core.Invalid):run(bad)
    def test_reject_illegal_typed_fields_ids_order_and_schema(self):
        mutations=[lambda d:d.update(schema=True),lambda d:d.update(replay_schema=3),lambda d:d['configurations'][0]['profile']['capabilities'].update(camera=1),lambda d:d['configurations'][0].update(assertions=None),lambda d:d['configurations'][1].update(id='Left'),lambda d:d['configurations'][0].update(id='../outside'),lambda d:d.update(extra=1),lambda d:d['configurations'][0].update(initial={}),lambda d:d['events'].extend([{'at_ms':2,'type':'wait'},{'at_ms':1,'type':'wait'}]),lambda d:d['configurations'][0].update(assertions=[{'after_event':0,'expect':{'connected':1}}])]
        for mutate in mutations:
            value=fixture();mutate(value)
            with self.subTest(mutate=mutate):
                with self.assertRaises(core.Invalid):run(value)
    def test_duplicate_nonfinite_deep_json_rejected(self):
        for raw in (b'{"schema":1,"schema":1}',b'{"x":NaN}',b'['*100+b'0'+b']'*100):
            with self.assertRaises(core.Invalid):compare.analyze(raw)
    def test_no_subprocess_or_socket_during_comparison(self):
        with patch.object(subprocess,'Popen',side_effect=AssertionError('execution')), patch.object(socket,'socket',side_effect=AssertionError('network')):
            self.assertIsNone(run(fixture())['first_divergence'])
    def test_plain_text_escapes_source_newlines_and_markup(self):
        value=fixture();value['events']=[notify('one')];value['events'][0]['text']='</script>\n![x](https://example.invalid)'
        report=run(value);text=compare.text_report(report).decode()
        self.assertIn('\\n',text);self.assertNotIn('</script>\n![x]',text)
        self.assertIn('![x]',text) # Plain text is not a Markdown or HTML sanitizer.


class BundleComparison(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
        self.source=self.p/'input.json';self.source.write_bytes(core.canonical(fixture()))
    def test_build_and_verify_preserve_exact_input_bytes(self):
        raw=self.source.read_bytes()+b'\n';self.source.write_bytes(raw)
        result=compare.build(self.source,self.p/'out');self.assertEqual(result,compare.verify(self.p/'out'))
        self.assertEqual((self.p/'out/source.json').read_bytes(),raw)
        if os.name=='posix':
            self.assertEqual((self.p/'out').stat().st_mode&0o777,0o700)
            for p in (self.p/'out').iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_tampered_member_and_extra_or_missing_rejected(self):
        for name in compare.FILES:
            out=self.p/name;compare.build(self.source,out);p=out/name;p.write_bytes(p.read_bytes()+b' ')
            with self.assertRaises(core.Invalid):compare.verify(out)
        out=self.p/'extra';compare.build(self.source,out);(out/'extra').write_bytes(b'synthetic')
        with self.assertRaises(core.Invalid):compare.verify(out)
        (out/'extra').unlink();(out/'comparison.txt').unlink()
        with self.assertRaises(core.Invalid):compare.verify(out)
    def test_report_integer_to_boolean_tamper_rejected(self):
        out=self.p/'out';compare.build(self.source,out)
        path=out/'comparison.json';v=json.loads(path.read_bytes());v['events'][0]['after_event']=False;path.write_bytes(core.canonical(v))
        with self.assertRaises(core.Invalid):compare.verify(out)
    def test_output_limit_preflight_and_input_limit(self):
        with patch.object(core,'OUTPUT_LIMIT',10):
            with self.assertRaises(core.Invalid):compare.build(self.source,self.p/'out')
        self.assertFalse((self.p/'out').exists())
        self.source.write_bytes(b' '*(core.INPUT_LIMIT+1))
        with self.assertRaises(core.Invalid):compare.build(self.source,self.p/'out')
        self.assertFalse((self.p/'out').exists())
    def test_existing_target_and_leaf_links_not_overwritten(self):
        target=self.p/'existing';target.mkdir();(target/'keep').write_bytes(b'keep')
        with self.assertRaises(FileExistsError):compare.build(self.source,target)
        self.assertEqual((target/'keep').read_bytes(),b'keep')
        link=self.p/'link'
        try:link.symlink_to(self.p/'absent',target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable')
        with self.assertRaises(FileExistsError):compare.build(self.source,link)
        self.assertFalse((self.p/'absent').exists())
        src=self.p/'source-link';src.symlink_to(self.source)
        with self.assertRaises(core.Invalid):compare.build(src,self.p/'out')
    def test_concurrent_output_has_one_winner(self):
        answers=[]
        def attempt():
            try:compare.build(self.source,self.p/'out');answers.append('ok')
            except FileExistsError:answers.append('exists')
        threads=[threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(answers),['exists','ok']);compare.verify(self.p/'out')
    def test_write_failure_retains_partial_not_verified(self):
        original=os.open
        def fail(path,*args,**kwargs):
            if Path(path).name=='comparison.txt':raise OSError('synthetic write failure')
            return original(path,*args,**kwargs)
        with patch.object(os,'open',side_effect=fail):
            with self.assertRaises(OSError):compare.build(self.source,self.p/'out')
        self.assertTrue((self.p/'out/source.json').exists())
        with self.assertRaises(core.Invalid):compare.verify(self.p/'out')
    def test_real_cli_no_assertions_and_pass_exit_gates(self):
        cmd=[sys.executable,'-m','glance_replay.compare']
        for label,asserted in [('empty',False),('asserted',True)]:
            value=fixture()
            if asserted:
                for c in value['configurations']:c['assertions']=[{'after_event':0,'expect':{'result':'waited'}}]
            self.source.write_bytes(core.canonical(value));out=self.p/label
            for args in (['build',str(self.source),'--out',str(out)],['verify',str(out)]):
                p=subprocess.run(cmd+args+['--require-all-pass'],cwd=ROOT,capture_output=True)
                self.assertEqual(p.returncode,0 if asserted else 3,p.stderr)
                self.assertEqual(json.loads(p.stdout)['all_assertions_pass'],asserted)
    def test_real_cli_invalid_does_not_echo_input_or_create_output(self):
        self.source.write_bytes(b'{"PRIVATE_SYNTHETIC_MARKER":true}')
        p=subprocess.run([sys.executable,'-m','glance_replay.compare','build',str(self.source),'--out',str(self.p/'out')],cwd=ROOT,capture_output=True)
        self.assertEqual(p.returncode,2);self.assertNotIn(b'PRIVATE_SYNTHETIC_MARKER',p.stderr+p.stdout)
        self.assertNotIn(b'Traceback',p.stderr);self.assertFalse((self.p/'out').exists())

if __name__=='__main__':unittest.main()
