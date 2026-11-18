"""Loopback-only, in-memory scenario workbench. No device or external service access."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from . import core

ASSETS=Path(__file__).parent/'assets'
ROUTES={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/example/notification':('notification-day.json','application/json'),'/example/platform':('platform-day.json','application/json')}

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,port=0):
        self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port),Handler)
    @property
    def authority(self):return '127.0.0.1:'+str(self.server_port)

class Handler(BaseHTTPRequestHandler):
    server_version='GlanceWorkbench'
    def log_message(self,*args):pass
    def setup(self):
        super().setup();self.connection.settimeout(5)
    def send(self,status,body,kind='application/json; charset=utf-8'):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header('Connection','close');self.end_headers();self.wfile.write(body);self.close_connection=True
    def fail(self,status):self.send(status,b'{"ok":false,"error":"Request rejected. Check scenario format, size and local origin."}')
    def allowed(self):
        hosts=self.headers.get_all('Host',[])
        if hosts != [self.server.authority]:return False
        origin=self.headers.get_all('Origin',[])
        if origin and origin!=['http://'+self.server.authority]:return False
        if self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):return False
        return True
    def do_GET(self):
        if not self.allowed():return self.fail(403)
        if self.path=='/session':return self.send(200,json.dumps({'token':self.server.token}).encode())
        asset=ROUTES.get(self.path)
        if not asset:return self.fail(404)
        self.send(200,(ASSETS/asset[0]).read_bytes(),asset[1])
    def do_POST(self):
        if not self.allowed():return self.fail(403)
        tokens=self.headers.get_all('X-Glance-Token',[])
        if len(tokens)!=1 or not tokens[0].isascii() or not hmac.compare_digest(tokens[0],self.server.token):return self.fail(403)
        if self.path!='/replay':return self.fail(404)
        lengths=self.headers.get_all('Content-Length',[])
        if self.headers.get('Transfer-Encoding') or len(lengths)!=1 or len(lengths[0])>7 or not lengths[0].isascii() or not lengths[0].isdigit():return self.fail(400)
        length=int(lengths[0])
        if length<1 or length>core.INPUT_LIMIT:return self.fail(413)
        if self.headers.get_all('Content-Type',[])!=['application/json']:return self.fail(415)
        try:
            raw=self.rfile.read(length)
            if len(raw)!=length:return self.fail(400)
            report=core.replay(raw);body=core.canonical(report)
            if len(body)>core.OUTPUT_LIMIT:return self.fail(413)
        except (ValueError,UnicodeError,RecursionError,OSError):return self.fail(400)
        self.send(200,body)
    def do_OPTIONS(self):self.fail(405)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',type=int,default=8765);parser.add_argument('--host',choices=['127.0.0.1'],default='127.0.0.1');parser.add_argument('--strictPort',action='store_true',help='Port binding is always strict');args=parser.parse_args()
    with Server(args.port) as server:
        print('Glance Replay workbench: http://'+server.authority,flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
if __name__=='__main__':main()
