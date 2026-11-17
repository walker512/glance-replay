"""Explicit hypothetical platform scenarios, not hardware/ASR integration tests."""
import copy,hashlib,itertools,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from glance_replay import core
ROOT=Path(__file__).resolve().parents[1]
def scenario():return {'schema':2,'profile':{'columns':16,'rows':2,'queue_limit':3,'low_battery_percent':10,'capabilities':{'camera':True,'microphone':True,'offline_voice':False,'background_companion':False}},'initial':{'connected':True,'worn':True,'permissions':['notifications','camera','microphone'],'battery_percent':80,'phone_app':'foreground','network':'online'},'events':[{'at_ms':0,'type':'wait'}],'assertions':[]}
def notify(id='one',origin='local',at=0):return {'at_ms':at,'type':'notify','id':id,'text':'Synthetic reminder','priority':1,'ttl_ms':1000,'origin':origin}
def run(d):return core.replay(core.canonical(d))
class PlatformTests(unittest.TestCase):
 def test_battery_zero_purges_and_restore_does_not_resurrect(self):
  d=scenario();d['events']=[notify(),{'at_ms':1,'type':'battery','percent':0},{'at_ms':2,'type':'battery','percent':80},{'at_ms':3,'type':'wait'}];r=run(d)['trace'];self.assertEqual(r[1]['removed_or_dropped'],['one']);self.assertFalse(r[1]['powered']);self.assertTrue(r[2]['powered']);self.assertEqual(r[3]['queue'],[])
 def test_low_battery_capture_boundary_notification_still_works(self):
  d=scenario();d['initial']['battery_percent']=10;d['events']=[notify(),{'at_ms':1,'type':'capture','resource':'camera'},{'at_ms':2,'type':'battery','percent':11},{'at_ms':3,'type':'capture','resource':'camera'}];r=run(d)['trace'];self.assertEqual(r[0]['result'],'notified');self.assertEqual(r[1]['result'],'denied_low_battery');self.assertEqual(r[3]['result'],'simulated_capture_allowed')
 def test_network_offline_blocks_remote_not_local_or_existing(self):
  d=scenario();d['events']=[notify('remote','remote'),{'at_ms':1,'type':'network','state':'offline'},notify('bad','remote',2),notify('local','local',3)];r=run(d)['trace'];self.assertEqual(r[1]['queue'],['remote']);self.assertEqual(r[2]['result'],'denied_network');self.assertEqual(r[3]['queue'],['remote','local'])
 def test_companion_stop_and_background_capability(self):
  for background in (False,True):
   d=scenario();d['profile']['capabilities']['background_companion']=background;d['events']=[notify(),{'at_ms':1,'type':'phone_app','state':'background'},notify('new','local',2),{'at_ms':3,'type':'phone_app','state':'stopped'},{'at_ms':4,'type':'phone_app','state':'foreground'}];r=run(d)['trace'];self.assertEqual(r[1]['queue'],['one'] if background else []);self.assertEqual(r[2]['result'],'notified' if background else 'denied_companion');self.assertEqual(r[3]['queue'],[]);self.assertEqual(r[4]['queue'],[])
 def test_voice_next_dismiss_and_camera_are_simulated(self):
  d=scenario();d['events']=[notify('one'),notify('two',at=1),{'at_ms':2,'type':'voice','command':'next'},{'at_ms':3,'type':'voice','command':'dismiss'},{'at_ms':4,'type':'voice','command':'capture_camera'}];r=run(d)['trace'];self.assertEqual(r[2]['active'],'two');self.assertEqual(r[3]['queue'],['one']);self.assertEqual(r[4]['result'],'simulated_capture_allowed');self.assertEqual(r[4]['event'],'voice');self.assertEqual(r[4]['voice_command'],'capture_camera')
 def test_voice_microphone_gate_before_capture_permission(self):
  d=scenario();d['initial']['permissions']=['camera','notifications'];d['events']=[{'at_ms':0,'type':'voice','command':'capture_camera'}];self.assertEqual(run(d)['trace'][0]['result'],'denied_permission')
 def test_voice_camera_requires_own_permission(self):
  d=scenario();d['initial']['permissions']=['microphone'];d['events']=[{'at_ms':0,'type':'voice','command':'capture_camera'}];self.assertEqual(run(d)['trace'][0]['result'],'denied_permission')
 def test_voice_network_and_offline_capability(self):
  for offline in (False,True):
   d=scenario();d['profile']['capabilities']['offline_voice']=offline;d['initial']['network']='offline';d['events']=[{'at_ms':0,'type':'voice','command':'next'}];self.assertEqual(run(d)['trace'][0]['result'],'no_notification' if offline else 'denied_network')
 def test_unsupported_camera_vs_permission(self):
  d=scenario();d['profile']['capabilities']['camera']=False;d['events']=[{'at_ms':0,'type':'capture','resource':'camera'}];self.assertEqual(run(d)['trace'][0]['result'],'denied_unsupported_resource')
 def test_physical_capture_is_not_phone_foreground_dependent(self):
  d=scenario();d['initial']['phone_app']='stopped';d['events']=[{'at_ms':0,'type':'capture','resource':'camera'},{'at_ms':1,'type':'voice','command':'capture_camera'}];r=run(d)['trace'];self.assertEqual(r[0]['result'],'simulated_capture_allowed');self.assertEqual(r[1]['result'],'denied_companion')
 def test_all_capture_gate_combinations(self):
  for battery,connected,worn,supported,permission in itertools.product((0,10,11),(False,True),(False,True),(False,True),(False,True)):
   d=scenario();d['initial'].update(battery_percent=battery,connected=connected,worn=worn,permissions=['camera'] if permission else []);d['profile']['capabilities']['camera']=supported;d['events']=[{'at_ms':0,'type':'capture','resource':'camera'}];expected='denied_powered_off' if battery==0 else 'denied_disconnected' if not connected else 'denied_not_worn' if not worn else 'denied_unsupported_resource' if not supported else 'denied_permission' if not permission else 'denied_low_battery' if battery<=10 else 'simulated_capture_allowed';self.assertEqual(run(d)['trace'][0]['result'],expected)
 def test_equal_timestamp_order_expiry_and_rejected_not_replayed(self):
  d=scenario();d['events']=[notify(),{'at_ms':1000,'type':'battery','percent':0},notify('dropped',at=1000),{'at_ms':1000,'type':'battery','percent':50}];r=run(d)['trace'];self.assertEqual(r[1]['expired'],['one']);self.assertEqual(r[2]['result'],'denied_powered_off');self.assertEqual(r[3]['queue'],[])
 def test_new_assertions_typed_and_no_assertions_not_pass(self):
  d=scenario();self.assertEqual(run(d)['status'],'no_assertions');d['assertions']=[{'after_event':0,'expect':{'battery_percent':80,'powered':True,'phone_app':'foreground','network':'online','voice_command':None}}];self.assertEqual(run(d)['status'],'pass');d['assertions'][0]['expect']['powered']=1
  with self.assertRaises(core.Invalid):run(d)
 def test_unknown_and_wrong_types_rejected(self):
  for mutate in (lambda d:d['initial'].update(battery_percent=True),lambda d:d['profile']['capabilities'].update(camera=1),lambda d:d['initial'].update(network='wifi'),lambda d:d['events'].__setitem__(0,{'at_ms':0,'type':'voice','command':'arbitrary text'}),lambda d:d['events'].__setitem__(0,notify()),lambda d:d['profile'].update(low_battery_percent=100)):
   d=scenario();mutate(d)
   if d['events'][0]['type']=='notify':d['events'][0].pop('origin')
   with self.assertRaises(core.Invalid):run(d)
 def test_v1_does_not_accept_platform_fields(self):
  d=json.loads((ROOT/'examples/notification-day.json').read_bytes());d['initial']['battery_percent']=80
  with self.assertRaises(core.Invalid):run(d)
 def test_v1_locked_example_byte_compatibility(self):
  r=core.replay((ROOT/'examples/notification-day.json').read_bytes());self.assertEqual(hashlib.sha256(core.canonical(r)).hexdigest(),'15f965c95ec09da7b3af1e1564e8f56897a0a5ec955fee51830c2f56e527f53a');self.assertEqual(hashlib.sha256(core.text_frames(r)).hexdigest(),'1a671e1382f4e23ea6e59f37397849fba4cfd452c528ea90f7a1cd18e698f0b7')
 def test_seeded_platform_safety_state_invariants(self):
  import random
  rng=random.Random(1414)
  for case in range(10):
   d=scenario();caps=d['profile']['capabilities'];caps.update({k:bool(rng.randrange(2)) for k in caps});d['events']=[]
   for i in range(200):
    typ=rng.choice(['notify','battery','phone_app','network','voice','capture','connect','disconnect','wear','remove','grant','revoke','tap','dismiss','wait']);e={'at_ms':i*10,'type':typ}
    if typ=='notify':e=notify('n'+str(i),rng.choice(['local','remote']),i*10)
    elif typ=='battery':e['percent']=rng.choice([0,10,11,80])
    elif typ=='phone_app':e['state']=rng.choice(['foreground','background','stopped'])
    elif typ=='network':e['state']=rng.choice(['online','offline'])
    elif typ=='voice':e['command']=rng.choice(core.VOICE_COMMANDS)
    elif typ=='capture':e['resource']=rng.choice(['camera','microphone'])
    elif typ in ('grant','revoke'):e['permission']=rng.choice(core.PERMISSIONS)
    d['events'].append(e)
   r=run(d)
   for e,row in zip(d['events'],r['trace']):
    companion=row['phone_app']=='foreground' or row['phone_app']=='background' and caps['background_companion']
    if not row['powered'] or not row['connected'] or not row['worn'] or not companion or 'notifications' not in row['permissions']:self.assertEqual(row['queue'],[])
    self.assertLessEqual(len(row['queue']),d['profile']['queue_limit']);self.assertEqual(len(row['queue']),len(set(row['queue'])))
    if row['result']=='simulated_capture_allowed':
     resource=e.get('resource') or ('camera' if e['command']=='capture_camera' else 'microphone')
     self.assertTrue(row['battery_percent']>10 and row['connected'] and row['worn'] and caps[resource] and resource in row['permissions'])
     if e['type']=='voice':self.assertTrue(caps['microphone'] and 'microphone' in row['permissions'] and companion and (row['network']=='online' or caps['offline_voice']))
 def test_real_cli_bundle_reproduction_and_tamper(self):
  d=scenario();d['assertions']=[{'after_event':0,'expect':{'battery_percent':80}}]
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'source.json').write_bytes(core.canonical(d))
   for args in [['replay',str(p/'source.json'),'--out',str(p/'out')],['verify',str(p/'out')]]:
    r=subprocess.run([sys.executable,'-m','glance_replay',*args,'--require-pass'],cwd=ROOT,capture_output=True);self.assertEqual(r.returncode,0,r.stderr)
   (p/'out'/'frames.txt').write_bytes(b'changed')
   with self.assertRaises(core.Invalid):core.verify(p/'out')
