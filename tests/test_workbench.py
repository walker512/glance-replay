"""Real loopback HTTP acceptance/security tests. Not browser or hardware tests."""
import http.client
import json
from pathlib import Path
import threading
import unittest
from glance_replay import core
from glance_replay.workbench import Server,ASSETS

class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=Server();cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path='/',method='GET',body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            connection.request(method,path,body=body,headers=headers or {})
            response=connection.getresponse();return response.status,dict(response.getheaders()),response.read()
        finally:connection.close()
    def post(self,raw,extra=None):
        headers={'Content-Type':'application/json','X-Glance-Token':self.server.token,'Origin':'http://'+self.server.authority}
        headers.update(extra or {});return self.request('/replay','POST',raw,headers)
    def test_assets_and_headers(self):
        for path in ('/','/app.js','/style.css','/example/notification','/example/platform'):
            status,headers,body=self.request(path);self.assertEqual(status,200);self.assertTrue(body)
            self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Frame-Options'],'DENY')
            self.assertNotIn('Access-Control-Allow-Origin',headers);self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
    def test_both_schemas_match_existing_engine(self):
        for name in ('notification-day.json','platform-day.json'):
            raw=(ASSETS/name).read_bytes();status,_,body=self.post(raw)
            self.assertEqual(status,200);self.assertEqual(json.loads(body),core.replay(raw))
    def test_session_token(self):
        status,_,body=self.request('/session');self.assertEqual(status,200);self.assertEqual(json.loads(body)['token'],self.server.token)
    def test_missing_and_wrong_token_rejected(self):
        raw=(ASSETS/'notification-day.json').read_bytes()
        self.assertEqual(self.request('/replay','POST',raw,{'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.post(raw,{'X-Glance-Token':'wrong'})[0],403)
    def test_bad_hosts_and_origins_block_get_and_post(self):
        for headers in ({'Host':'evil.test'},{'Host':'localhost:'+str(self.server.server_port)},{'Origin':'null'},{'Origin':'https://evil.test'},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('/session',headers=headers)[0],403)
            self.assertEqual(self.post(b'{}',headers)[0],403)
    def test_same_origin_and_site_accepted(self):
        self.assertEqual(self.request('/',headers={'Origin':'http://'+self.server.authority,'Sec-Fetch-Site':'same-origin'})[0],200)
    def test_no_paths_or_arbitrary_static_files(self):
        for path in ('/../README.md','/assets/../core.py','/?x=1','/not-found'):
            self.assertEqual(self.request(path)[0],404)
    def test_invalid_input_returns_generic_error(self):
        for raw in (b'PRIVATE contents',b'{}',b'\xff',b'[]'):
            status,_,body=self.post(raw);self.assertEqual(status,400);self.assertNotIn(b'PRIVATE',body)
    def test_oversize_and_content_type(self):
        self.assertEqual(self.post(b'{}',{'Content-Length':str(core.INPUT_LIMIT+1)})[0],413)
        self.assertEqual(self.post(b'{}',{'Content-Type':'text/plain'})[0],415)
    def test_chunked_and_options_rejected(self):
        self.assertEqual(self.post(b'{}',{'Transfer-Encoding':'chunked'})[0],400)
        self.assertEqual(self.request('/replay','OPTIONS')[0],405)
    def test_duplicate_host_token_and_length_rejected(self):
        for field,value in [('Host',self.server.authority),('X-Glance-Token',self.server.token),('Content-Length','2')]:
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            try:
                connection.putrequest('POST','/replay',skip_host=True)
                headers={'Host':self.server.authority,'Content-Type':'application/json','Content-Length':'2','X-Glance-Token':self.server.token}
                for k,v in headers.items():connection.putheader(k,v)
                connection.putheader(field,value);connection.endheaders(b'{}');response=connection.getresponse()
                self.assertIn(response.status,(400,403));response.read()
            finally:connection.close()
    def test_untrusted_notification_is_only_json_data(self):
        raw=json.loads((ASSETS/'notification-day.json').read_text());event=next(e for e in raw['events'] if e['type']=='notify');event['text']='<img src=x onerror=alert(1)>';raw['assertions']=[]
        status,_,body=self.post(core.canonical(raw));self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'no_assertions')
    def test_frontend_has_no_html_injection_or_remote_assets(self):
        script=(ASSETS/'app.js').read_text();html=(ASSETS/'index.html').read_text()
        for sink in ('innerHTML','outerHTML','insertAdjacentHTML','eval(','localStorage','sessionStorage'):self.assertNotIn(sink,script)
        self.assertNotIn('https://',html);self.assertIn('mine!==revision',script);self.assertIn('controller.abort()',script)

    def test_hostile_header_values_return_generic_errors(self):
        self.assertEqual(self.post(b'{}',{'Content-Length':'9'*5000})[0],400)
        self.assertEqual(self.post(b'{}',{'X-Glance-Token':'é'})[0],403)
