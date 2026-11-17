"""Original synthetic event scenarios; never device SDK or hardware tests."""
import copy,json,os,random,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from glance_replay.core import *
ROOT=Path(__file__).resolve().parents[1]
SAMPLE=(ROOT/'examples/notification-day.json').read_bytes()
def event(t,kind,**extra):return dict(at_ms=t,type=kind,**extra)
def note(t,id,priority=1,ttl=100,text='hello'):return event(t,'notify',id=id,text=text,priority=priority,ttl_ms=ttl)
def scenario(events,queue=3,initial=None,assertions=None):return {'schema':1,'profile':{'columns':8,'rows':2,'queue_limit':queue},'initial':initial or {'connected':True,'worn':True,'permissions':['notifications']},'events':events,'assertions':assertions or []}
def trace(events,**kw):return replay(canonical(scenario(events,**kw)))['trace']
class Tests(unittest.TestCase):
    def test_example_assertions_pass(self):self.assertEqual(replay(SAMPLE)['status'],'pass')
    def test_priority_preempts_and_tap_cycles(self):
        r=trace([note(0,'low'),note(1,'urgent',9),event(2,'tap'),event(3,'tap')]);self.assertEqual([x['active'] for x in r],['low','urgent','low','urgent'])
    def test_equal_priority_fifo_no_preemption(self):
        r=trace([note(0,'a'),note(0,'b'),note(0,'c')]);self.assertEqual(r[-1]['queue'],['a','b','c']);self.assertEqual(r[-1]['active'],'a')
    def test_capacity_drops_low_priority_and_eviction(self):
        r=trace([note(0,'a',5),note(1,'b',1),note(2,'c',0),note(3,'d',9)],queue=2)
        self.assertEqual(r[2]['result'],'dropped_capacity');self.assertEqual(r[2]['removed_or_dropped'],['c']);self.assertEqual(r[-1]['removed_or_dropped'],['b']);self.assertEqual(r[-1]['queue'],['d','a'])
    def test_capacity_tie_keeps_earlier(self):
        r=trace([note(0,'a'),note(0,'b')],queue=1);self.assertEqual(r[-1]['result'],'dropped_capacity');self.assertEqual(r[-1]['active'],'a')
    def test_expiry_before_event_at_exact_boundary(self):
        r=trace([note(0,'a',ttl=10),event(9,'wait'),event(10,'tap')]);self.assertEqual(r[1]['active'],'a');self.assertEqual(r[2]['expired'],['a']);self.assertEqual(r[2]['result'],'no_notification')
    def test_expiry_frees_capacity_before_new_notify(self):
        r=trace([note(0,'a',ttl=1),note(1,'b')],queue=1);self.assertEqual(r[-1]['queue'],['b']);self.assertEqual(r[-1]['result'],'notified')
    def test_remove_and_disconnect_purge_no_resurrection(self):
        for action,restore in [('remove','wear'),('disconnect','connect')]:
            r=trace([note(0,'a'),event(1,action),event(2,restore)]);self.assertEqual(r[1]['removed_or_dropped'],['a']);self.assertEqual(r[-1]['queue'],[]);self.assertEqual(r[-1]['screen'],[])
    def test_notification_permission_revoke_purges(self):
        r=trace([note(0,'a'),event(1,'revoke',permission='notifications'),event(2,'grant',permission='notifications')]);self.assertEqual(r[-1]['screen'],[])
    def test_other_permission_revoke_preserves_notifications(self):
        r=trace([note(0,'a'),event(1,'revoke',permission='camera')]);self.assertEqual(r[-1]['active'],'a')
    def test_denial_order_and_dropped_not_queued(self):
        for state,result in [({'connected':False,'worn':False,'permissions':[]},'denied_disconnected'),({'connected':True,'worn':False,'permissions':[]},'denied_not_worn'),({'connected':True,'worn':True,'permissions':[]},'denied_permission')]:
            r=trace([note(0,'a')],initial=state)[0];self.assertEqual(r['result'],result);self.assertEqual(r['queue'],[])
    def test_mock_capture_never_returns_real_data(self):
        r=trace([event(0,'capture',resource='camera'),event(1,'grant',permission='camera'),event(2,'capture',resource='camera'),event(3,'remove'),event(4,'capture',resource='camera')]);self.assertEqual([x['result'] for x in r],['denied_permission','granted','simulated_capture_allowed','removed','denied_not_worn']);self.assertNotIn('image',r[2])
    def test_dismiss_selected_then_next_priority(self):
        r=trace([note(0,'a',2),note(1,'b',1),event(2,'tap'),event(3,'dismiss')]);self.assertEqual(r[-1]['removed_or_dropped'],['b']);self.assertEqual(r[-1]['active'],'a')
    def test_empty_gestures_noop(self):
        self.assertEqual([r['result'] for r in trace([event(0,'tap'),event(0,'dismiss')])],['no_notification']*2)
    def test_wrap_truncation_explicit(self):
        self.assertEqual(wrap('abcdefghijklmnopq',8,2),(['abcdefgh','ijklmno…'],True));self.assertEqual(wrap('中文学习\nsecond',4,2),(['中文学习','sec…'],True));self.assertEqual(wrap('a\n',4,2),(['a',''],False))
    def test_no_assertions_not_pass_gate(self):
        r=replay(canonical(scenario([event(0,'wait')])));self.assertEqual(r['status'],'no_assertions')
    def test_false_assertion_keeps_actual_evidence(self):
        d=scenario([note(0,'a')],assertions=[{'after_event':0,'expect':{'active':None}}]);r=replay(canonical(d));self.assertEqual(r['status'],'fail');self.assertEqual(r['assertions'][0]['actual'],{'active':'a'})
    def test_random_retention_oracle(self):
        rng=random.Random(92)
        for _ in range(100):
            events=[];items=[];capacity=rng.randint(1,8)
            for i in range(20):
                priority=rng.randint(0,9);events.append(note(i,'n'+str(i),priority,ttl=1000));items.append((priority,i,'n'+str(i)))
                items=sorted(items,key=lambda x:(-x[0],x[1]))[:capacity]
                observed=trace(events,queue=capacity)[-1]['queue'];self.assertEqual(observed,[x[2] for x in items])
    def test_bad_order_and_bool_number(self):
        for events in [[event(2,'wait'),event(1,'wait')],[event(True,'wait')],[note(0,'a',True)],[note(0,'a',ttl=0)]]:
            with self.assertRaises(Invalid):replay(canonical(scenario(events)))
    def test_duplicate_ids_even_after_expiry(self):
        with self.assertRaises(Invalid):replay(canonical(scenario([note(0,'a',ttl=1),note(2,'a')])))
    def test_invalid_profile_and_permission(self):
        for change in [lambda d:d['profile'].update(rows=0),lambda d:d['profile'].update(columns=True),lambda d:d['profile'].update(queue_limit=33),lambda d:d['initial'].update(connected=1),lambda d:d['initial'].update(permissions=['notifications','notifications']),lambda d:d['initial'].update(permissions=['root'])]:
            d=scenario([event(0,'wait')]);change(d)
            with self.assertRaises(Invalid):replay(canonical(d))
    def test_control_format_unknown_fields_rejected(self):
        for text in ['secret\x1b[31m','text\u202e','a\0','x'*401]:
            with self.assertRaises(Invalid):replay(canonical(scenario([note(0,'a',text=text)])))
        d=scenario([event(0,'wait')]);d['events'][0]['command']='unused'
        with self.assertRaises(Invalid):replay(canonical(d))
    def test_assertion_types_and_unknown_fields(self):
        for expected in [{'connected':1},{'result':'real_photo'},{'queue':['a','a']},{'screen':[True]},{'typo':True}]:
            with self.assertRaises(Invalid):replay(canonical(scenario([event(0,'wait')],assertions=[{'after_event':0,'expect':expected}])))
    def test_json_adversarial(self):
        for raw in [b'{"x":1,"x":2}',b'['*20000+b'0'+b']'*20000,b'{"x":1e999}',b'"\\ud800"','{}'.encode('utf-16')]:
            with self.assertRaises(Invalid):replay(raw)
    def test_maximum_event_and_text_roundtrip(self):
        d=scenario([note(i,'n'+str(i),i%10,ttl=10000,text='字'*400) for i in range(500)],queue=32);d['profile'].update(columns=80,rows=8)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'source';p.write_bytes(canonical(d));r=build(p,root/'out');self.assertEqual(len(r['trace']),500);self.assertEqual(verify(root/'out'),r)
    def test_exact_bytes_source_crlf_and_tamper(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'source';p.write_bytes(SAMPLE.replace(b'\n',b'\r\n'))
            with patch.object(Path,'write_text',side_effect=AssertionError('no text writes')):r=build(p,root/'out')
            self.assertEqual((root/'out/source.json').read_bytes(),p.read_bytes());self.assertEqual(verify(root/'out'),r)
            (root/'out/report.json').write_bytes(canonical(r)+b'\n')
            with self.assertRaises(Invalid):verify(root/'out')
    def test_extra_no_overwrite_and_output_bound(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)/'out';build(ROOT/'examples/notification-day.json',out)
            with self.assertRaises(FileExistsError):build(ROOT/'examples/notification-day.json',out)
            (out/'extra').write_bytes(b'x')
            with self.assertRaises(Invalid):verify(out)
        with tempfile.TemporaryDirectory() as t,patch('glance_replay.core.OUTPUT_LIMIT',1):
            out=Path(t)/'out'
            with self.assertRaises(Invalid):build(ROOT/'examples/notification-day.json',out)
            self.assertFalse(out.exists())
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'link'
            try:p.symlink_to(ROOT/'examples/notification-day.json')
            except OSError:self.skipTest('OS disallows symlinks')
            with self.assertRaises(Invalid):read(p)
    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO unavailable')
    def test_fifo_cli_bounded_no_private_echo(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'PRIVATE_SENTINEL';os.mkfifo(p)
            r=subprocess.run([sys.executable,'-m','glance_replay','replay',str(p),'--out',str(Path(t)/'out')],cwd=ROOT,capture_output=True,text=True,timeout=2)
            self.assertEqual(r.returncode,2);self.assertNotIn('PRIVATE_SENTINEL',r.stderr);self.assertNotIn('Traceback',r.stderr)
    def test_cli_pass_and_no_assertion_gate(self):
        for empty,code in [(False,0),(True,3)]:
            with tempfile.TemporaryDirectory() as t:
                root=Path(t);source=root/'s';d=json.loads(SAMPLE)
                if empty:d['assertions']=[]
                source.write_bytes(canonical(d))
                for args in [['replay',str(source),'--out',str(root/'out'),'--require-pass'],['verify',str(root/'out'),'--require-pass']]:
                    r=subprocess.run([sys.executable,'-m','glance_replay',*args],cwd=ROOT,capture_output=True,text=True);self.assertEqual(r.returncode,code,r.stderr)
if __name__=='__main__':unittest.main()
