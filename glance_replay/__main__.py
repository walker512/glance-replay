import argparse,json,sys
from .core import build,verify,Invalid

def main():
    p=argparse.ArgumentParser(description='Offline hypothetical glance-app event replay; no device connection.')
    s=p.add_subparsers(dest='command',required=True)
    r=s.add_parser('replay');r.add_argument('source');r.add_argument('--out',required=True);r.add_argument('--require-pass',action='store_true')
    v=s.add_parser('verify');v.add_argument('folder');v.add_argument('--require-pass',action='store_true')
    a=p.parse_args()
    try:
        r=build(a.source,a.out) if a.command=='replay' else verify(a.folder)
        print(json.dumps({'consistent':True,'events':len(r['trace']),'status':r['status'],'scope':r['scope']}));return 3 if a.require_pass and r['status']!='pass' else 0
    except (Invalid,OSError,ValueError,RecursionError):
        print('Cannot process bounded replay: invalid input, inconsistent outputs or filesystem failure. Input text is not echoed.',file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
