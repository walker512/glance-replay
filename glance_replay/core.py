"""Synthetic event simulator for one explicitly specified glance app."""
import hashlib,io,json,os,re,stat
from pathlib import Path
INPUT_LIMIT=1024*1024
OUTPUT_LIMIT=8*1024*1024
class Invalid(ValueError):pass

def read(path,limit=INPUT_LIMIT):
    try:
        if not stat.S_ISREG(Path(path).lstat().st_mode):raise Invalid('Regular non-symlink file required.')
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NONBLOCK',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise Invalid('File type or size limit exceeded.')
            with os.fdopen(fd,'rb') as f:fd=None;raw=f.read(limit+1)
        finally:
            if fd is not None:os.close(fd)
        if len(raw)>limit:raise Invalid('File size limit exceeded.')
        raw.decode('utf8');return raw
    except (OSError,UnicodeError):raise Invalid('Cannot safely read bounded UTF-8 file.') from None

def parse(raw):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise Invalid('Duplicate JSON keys.')
            k.encode('utf8');result[k]=v
        return result
    def bad(x):raise Invalid('Non-finite number.')
    try:
        if len(raw)>INPUT_LIMIT:raise Invalid('Input exceeds 1 MiB.')
        result=json.loads(raw.decode('utf8'),object_pairs_hook=pairs,parse_constant=bad)
        queue=[(result,0)]
        while queue:
            value,depth=queue.pop()
            if isinstance(value,(list,dict)):
                if depth>=16:raise Invalid('JSON depth exceeded.')
                queue.extend((v,depth+1) for v in (value.values() if isinstance(value,dict) else value))
            elif isinstance(value,str):value.encode('utf8')
            elif isinstance(value,float):raise Invalid('Only integer ticks are supported.')
        return result
    except (ValueError,UnicodeError,RecursionError):raise Invalid('Invalid bounded JSON.') from None

def fields(item,names):
    if not isinstance(item,dict) or set(item)!=set(names):raise Invalid('Unexpected or missing fields.')
def integer(value,lo,hi):
    if type(value) is not int or not lo<=value<=hi:raise Invalid('Integer outside declared bounds.')
def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_.-]{0,47}',value):raise Invalid('Invalid identifier.')
import unicodedata
PERMISSIONS=('notifications','camera','microphone')
RESULTS=('connected','disconnected','worn','removed','granted','revoked','notified','dropped_capacity','denied_disconnected','denied_not_worn','denied_permission','cycled','dismissed','no_notification','simulated_capture_allowed','waited')
def plain(x,maximum=400):
    if type(x) is not str or not 1<=len(x)<=maximum or any(unicodedata.category(c).startswith('C') and c!='\n' for c in x):raise Invalid('Expected bounded display text without control/format characters.')
PLATFORM_RESULTS=('battery_changed','network_changed','phone_app_changed','denied_powered_off','denied_low_battery','denied_unsupported_resource','denied_companion','denied_network')
VOICE_COMMANDS=('next','dismiss','capture_camera','capture_microphone')
def load(raw):
    d=parse(raw);fields(d,['schema','profile','initial','events','assertions']);integer(d['schema'],1,2);v2=d['schema']==2
    fields(d['profile'],['columns','rows','queue_limit']+(['capabilities','low_battery_percent'] if v2 else []));integer(d['profile']['columns'],4,80);integer(d['profile']['rows'],1,8);integer(d['profile']['queue_limit'],1,32)
    fields(d['initial'],['connected','worn','permissions']+(['battery_percent','phone_app','network'] if v2 else []))
    if v2:
        caps=d['profile']['capabilities'];fields(caps,['camera','microphone','offline_voice','background_companion'])
        if any(type(v) is not bool for v in caps.values()):raise Invalid('Capabilities must be hypothetical boolean declarations.')
        integer(d['profile']['low_battery_percent'],0,99);integer(d['initial']['battery_percent'],0,100)
        if d['initial']['phone_app'] not in ('foreground','background','stopped') or d['initial']['network'] not in ('online','offline'):raise Invalid('Unknown platform initial state.')
    for flag in ('connected','worn'):
        if type(d['initial'][flag]) is not bool:raise Invalid('Initial flags must be boolean.')
    ps=d['initial']['permissions']
    if not isinstance(ps,list) or any(type(p) is not str or p not in PERMISSIONS for p in ps) or len(ps)!=len(set(ps)):raise Invalid('Invalid or duplicate permission.')
    if not isinstance(d['events'],list) or not 1<=len(d['events'])<=500:raise Invalid('Expected 1..500 events.')
    prev=-1;ids=set()
    for e in d['events']:
        if not isinstance(e,dict) or type(e.get('type')) is not str:raise Invalid('Invalid event.')
        typ=e['type'];extra=[]
        if typ in ('grant','revoke'):extra=['permission']
        elif typ=='notify':extra=['id','text','priority','ttl_ms']+(['origin'] if v2 else [])
        elif typ=='capture':extra=['resource']
        elif v2 and typ=='battery':extra=['percent']
        elif v2 and typ in ('network','phone_app'):extra=['state']
        elif v2 and typ=='voice':extra=['command']
        elif typ not in ('connect','disconnect','wear','remove','tap','dismiss','wait'):raise Invalid('Unknown event type.')
        fields(e,['at_ms','type',*extra]);integer(e['at_ms'],0,86400000)
        if e['at_ms']<prev:raise Invalid('Events must have nondecreasing timestamps.')
        prev=e['at_ms']
        if typ in ('grant','revoke') and (type(e['permission']) is not str or e['permission'] not in PERMISSIONS):raise Invalid('Unknown permission.')
        if typ=='capture' and (type(e['resource']) is not str or e['resource'] not in ('camera','microphone')):raise Invalid('Unsupported mock resource.')
        if v2:
            if typ=='battery':integer(e['percent'],0,100)
            if typ=='network' and e['state'] not in ('online','offline'):raise Invalid('Unknown network state.')
            if typ=='phone_app' and e['state'] not in ('foreground','background','stopped'):raise Invalid('Unknown companion state.')
            if typ=='voice' and e['command'] not in VOICE_COMMANDS:raise Invalid('Unknown simulated recognized voice intent.')
            if typ=='notify' and e['origin'] not in ('local','remote'):raise Invalid('Notification origin must be local or remote.')
        if typ=='notify':
            identifier(e['id']);plain(e['text']);integer(e['priority'],0,9);integer(e['ttl_ms'],1,3600000)
            if e['id'] in ids:raise Invalid('Notification IDs must be unique for the entire scenario.')
            ids.add(e['id'])
    if not isinstance(d['assertions'],list) or len(d['assertions'])>500:raise Invalid('At most 500 assertions.')
    for a in d['assertions']:
        fields(a,['after_event','expect']);integer(a['after_event'],0,len(d['events'])-1);x=a['expect']
        if not isinstance(x,dict) or not x or not set(x)<=({'connected','worn','permissions','active','queue','screen','result'}|({'battery_percent','powered','phone_app','network','voice_command'} if v2 else set())):raise Invalid('Invalid assertion fields.')
        for k,v in x.items():
            if k in ('connected','worn','powered'):
                if type(v) is not bool:raise Invalid('Assertion flags must be boolean.')
            elif k=='battery_percent':integer(v,0,100)
            elif k=='phone_app':
                if v not in ('foreground','background','stopped'):raise Invalid('Invalid companion assertion.')
            elif k=='network':
                if v not in ('online','offline'):raise Invalid('Invalid network assertion.')
            elif k=='voice_command':
                if v is not None and v not in VOICE_COMMANDS:raise Invalid('Invalid voice intent assertion.')
            elif k=='active':
                if v is not None:identifier(v)
            elif k in ('queue','permissions'):
                if not isinstance(v,list) or len(v)>32 or any(type(t) is not str for t in v) or len(v)!=len(set(v)):raise Invalid('Invalid assertion list.')
                for t in v:
                    if k=='queue':identifier(t)
                    elif t not in PERMISSIONS:raise Invalid('Invalid expected permission.')
            elif k=='screen':
                if not isinstance(v,list) or len(v)>8:raise Invalid('Invalid screen assertion.')
                for text in v:
                    if text!='':plain(text,80)
            elif type(v) is not str or v not in RESULTS+(PLATFORM_RESULTS if v2 else ()):raise Invalid('Unknown result assertion.')
    return d

def canonical(x):return (json.dumps(x,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n').encode('utf8')
def wrap(text,columns,rows):
    lines=[]
    for line in text.split('\n'):lines.extend([line[i:i+columns] for i in range(0,len(line),columns)] or [''])
    truncated=len(lines)>rows;lines=lines[:rows]
    if truncated:lines[-1]=lines[-1][:columns-1]+'…'
    return lines,truncated

def replay(raw):
    d=load(raw);connected=d['initial']['connected'];worn=d['initial']['worn'];permissions=set(d['initial']['permissions']);queue=[];active=None;trace=[]
    v2=d['schema']==2;cap=d['profile'].get('capabilities',{});battery=d['initial'].get('battery_percent',100);phone=d['initial'].get('phone_app','foreground');network=d['initial'].get('network','online')
    def companion_blocked():return phone=='stopped' or phone=='background' and not cap.get('background_companion',False)
    def ordered(items):return sorted(items,key=lambda x:(-x['priority'],x['sequence']))
    for seq,e in enumerate(d['events']):
        now=e['at_ms'];expired=[x['id'] for x in ordered(queue) if x['expires_ms']<=now];queue=[x for x in queue if x['expires_ms']>now]
        if active not in {x['id'] for x in queue}:active=ordered(queue)[0]['id'] if queue else None
        typ=e['type'];removed=[]
        def denied(permission):
            return 'denied_powered_off' if v2 and battery==0 else 'denied_disconnected' if not connected else 'denied_not_worn' if not worn else 'denied_unsupported_resource' if v2 and permission in ('camera','microphone') and not cap[permission] else 'denied_permission' if permission not in permissions else 'denied_low_battery' if v2 and permission in ('camera','microphone') and battery<=d['profile']['low_battery_percent'] else None
        resource=e.get('resource')
        if typ=='voice':
            result=denied('microphone') or ('denied_companion' if companion_blocked() else 'denied_network' if network=='offline' and not cap['offline_voice'] else None)
            if result is not None:typ='blocked_voice'
            else:
                command=e['command'];typ='tap' if command=='next' else 'dismiss' if command=='dismiss' else 'capture';resource='camera' if command=='capture_camera' else 'microphone'
        if typ=='connect':connected=True;result='connected'
        elif typ=='disconnect':connected=False;result='disconnected';removed=[x['id'] for x in ordered(queue)];queue=[];active=None
        elif typ=='wear':worn=True;result='worn'
        elif typ=='remove':worn=False;result='removed';removed=[x['id'] for x in ordered(queue)];queue=[];active=None
        elif typ=='grant':permissions.add(e['permission']);result='granted'
        elif typ=='revoke':
            permissions.discard(e['permission']);result='revoked'
            if e['permission']=='notifications':removed=[x['id'] for x in ordered(queue)];queue=[];active=None
        elif typ=='notify':
            result=denied('notifications')
            if v2 and result is None:result='denied_companion' if companion_blocked() else 'denied_network' if e['origin']=='remote' and network=='offline' else None
            if result is None:
                candidate={'id':e['id'],'text':e['text'],'priority':e['priority'],'expires_ms':now+e['ttl_ms'],'sequence':seq}
                ranked=ordered(queue+[candidate]);kept=ranked[:d['profile']['queue_limit']];removed=[x['id'] for x in ranked[d['profile']['queue_limit']:]];queue=kept
                if e['id'] not in {x['id'] for x in queue}:result='dropped_capacity'
                else:result='notified'
                current=next((x for x in queue if x['id']==active),None)
                if current is None or (result=='notified' and candidate['priority']>current['priority']):active=ordered(queue)[0]['id'] if queue else None
        elif typ=='tap':
            ranked=ordered(queue)
            if ranked:
                ids=[x['id'] for x in ranked];active=ids[(ids.index(active)+1)%len(ids)];result='cycled'
            else:result='no_notification'
        elif typ=='dismiss':
            if active is None:result='no_notification'
            else:removed=[active];queue=[x for x in queue if x['id']!=active];active=ordered(queue)[0]['id'] if queue else None;result='dismissed'
        elif typ=='capture':result=denied(resource) or 'simulated_capture_allowed'
        elif typ=='blocked_voice':pass
        elif typ=='battery':
            battery=e['percent'];result='battery_changed'
            if battery==0:removed=[x['id'] for x in ordered(queue)];queue=[];active=None
        elif typ=='network':network=e['state'];result='network_changed'
        elif typ=='phone_app':
            phone=e['state'];result='phone_app_changed'
            if companion_blocked():removed=[x['id'] for x in ordered(queue)];queue=[];active=None
        else:result='waited'
        chosen=next((x for x in queue if x['id']==active),None)
        screen,truncated=wrap(chosen['text'],d['profile']['columns'],d['profile']['rows']) if chosen is not None else ([],False)
        trace.append({'after_event':seq,'at_ms':now,'event':e['type'],'connected':connected,'worn':worn,'permissions':sorted(permissions),'queue':[x['id'] for x in ordered(queue)],'active':active,'screen':screen,'truncated':truncated,'expired':expired,'removed_or_dropped':removed,'result':result})
        if v2:trace[-1].update(battery_percent=battery,powered=battery>0,phone_app=phone,network=network,voice_command=e.get('command') if e['type']=='voice' else None)
    checks=[]
    for a in d['assertions']:
        actual={k:trace[a['after_event']][k] for k in a['expect']}
        checks.append({'after_event':a['after_event'],'expected':a['expect'],'actual':actual,'passed':canonical(actual)==canonical(a['expect'])})
    return {'schema':d['schema'],'policy':'glance-platform-v2' if v2 else 'glance-notifications-v1','source_sha256':hashlib.sha256(raw).hexdigest(),'profile':d['profile'],'trace':trace,'assertions':checks,'status':'no_assertions' if not checks else 'pass' if all(x['passed'] for x in checks) else 'fail','scope':('Hypothetical companion/battery/network and recognized-voice-intent policy; no ASR, device SDK, real energy model, phone UI or sensor capture.' if v2 else 'One hypothetical notification-app state machine; not a real device emulator, SDK adapter, permissions guarantee or camera/microphone capture.')}

def text_frames(report):
    lines=['GLANCE REPLAY — HYPOTHETICAL CHARACTER GRID',report['scope'],'Assertion status: '+report['status'],'']
    for r in report['trace']:
        lines+=['Event '+str(r['after_event'])+' at '+str(r['at_ms'])+' ms: '+r['event']+' → '+r['result'],'active='+str(r['active'])+'; queue='+','.join(r['queue'])+'; truncated='+str(r['truncated'])]
        if report['schema']==2:lines.append('battery='+str(r['battery_percent'])+'; powered='+str(r['powered'])+'; phone_app='+r['phone_app']+'; network='+r['network']+'; simulated_voice_intent='+str(r['voice_command']))
        lines.extend('| '+x for x in r['screen']);lines.append('')
    return '\n'.join(lines).encode('utf8')
def build(source,out):
    raw=read(source);report=replay(raw);files={'source.json':raw,'report.json':canonical(report),'frames.txt':text_frames(report)}
    if any(len(v)>OUTPUT_LIMIT for v in files.values()):raise Invalid('Output limit exceeded.')
    root=Path(out);root.mkdir(exist_ok=False)
    for n,v in files.items():(root/n).write_bytes(v)
    return report

def verify(folder):
    root=Path(folder)
    if root.is_symlink() or not root.is_dir() or {p.name for p in root.iterdir()}!={'source.json','report.json','frames.txt'}:raise Invalid('Unexpected replay structure.')
    report=replay(read(root/'source.json'))
    if read(root/'report.json',OUTPUT_LIMIT)!=canonical(report) or read(root/'frames.txt',OUTPUT_LIMIT)!=text_frames(report):raise Invalid('Replay output differs from source.')
    return report
