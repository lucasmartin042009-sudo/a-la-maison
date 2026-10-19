import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import quote
from server import Service, PUBLIC_ORIGIN, PUBLIC_HOST

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.root, self.state = base/'files', base/'state'
        self.family = base/'family'
        self.static = base/'web'
        self.static.mkdir()
        (self.static/'index.html').write_text('test')
        self.service = Service(('127.0.0.1', 0), self.static, self.root, self.state, 1024, family_root=self.family)
        self.thread = threading.Thread(target=self.service.serve_forever, daemon=True)
        self.thread.start()
        self.cookie, self.csrf = '', ''
        self.refresh()
        self.password = os.urandom(20).hex()  # temporary, never printed or persisted beyond TemporaryDirectory

    def tearDown(self):
        self.service.shutdown()
        self.service.server_close()
        self.temp.cleanup()

    def request(self, method, path, data=None, raw=None, headers=None):
        body = json.dumps(data).encode() if data is not None else raw
        h={'Cookie':self.cookie, 'Host': PUBLIC_HOST,
           'X-Forwarded-Host': PUBLIC_HOST, 'X-Forwarded-Proto': 'https'}
        if method=='POST':
            h.update({'Origin':self.service.origin, 'X-CSRF-Token':self.csrf, 'Content-Type':'application/json' if data is not None else 'application/octet-stream'})
        h.update(headers or {})
        c=http.client.HTTPConnection('127.0.0.1', self.service.server_port, timeout=5)
        c.request(method,path,body,h)
        r=c.getresponse()
        status, result = r.status, r.read()
        self.response_headers = dict(r.getheaders())
        if r.getheader('Set-Cookie'):
            self.cookie=r.getheader('Set-Cookie').split(';')[0]
        c.close()
        return status,result

    def refresh(self):
        status,data=self.request('GET','/api/session')
        self.assertEqual(status,200)
        result=json.loads(data)
        self.csrf=result['csrf']
        return result

    def setup_user(self):
        self.assertEqual(self.request('POST','/api/setup',{'user':'test','password':self.password})[0],200)
        self.assertTrue(self.refresh()['authenticated'])

    def test_auth_session_logout_and_expiry(self):
        self.assertEqual(self.request('GET','/api/files')[0],401)
        self.setup_user()
        record=json.loads((self.state/'accounts.json').read_text())['accounts'][0]
        self.assertNotIn(self.password,(self.state/'accounts.json').read_text())
        self.assertEqual(record['algorithm'],'scrypt-n16384-r8-p1-dk32')
        self.assertEqual((self.state/'accounts.json').stat().st_mode & 0o777,0o600)
        self.assertEqual(self.request('POST','/api/setup',{'user':'other','password':self.password})[0],409)
        self.assertEqual(self.request('POST','/api/logout',{})[0],200)
        self.assertEqual(self.request('GET','/api/files')[0],401)
        self.refresh()
        self.assertEqual(self.request('POST','/api/login',{'user':'test','password':'incorrect-password'})[0],401)
        self.assertEqual(self.request('POST','/api/login',{'user':'test','password':self.password})[0],200)
        self.refresh()
        sid=self.cookie.split('=',1)[1]
        self.service.sessions[sid]['expires']=0
        self.assertEqual(self.request('GET','/api/files')[0],401)

    def test_files_navigation_upload_download_collision(self):
        self.setup_user()
        self.assertEqual(self.request('POST','/api/folders',{'name':'Essai'})[0],201)
        self.assertEqual(self.request('POST','/api/folders',{'name':'Essai'})[0],409)
        payload='Texte de test — été\n<script>alert(1)</script>'.encode()
        endpoint='/api/upload?path=Essai&name='+quote('été.txt')
        self.assertEqual(self.request('POST',endpoint,raw=payload)[0],201)
        self.assertEqual(self.request('POST',endpoint,raw=b'overwrite')[0],409)
        status,data=self.request('GET','/api/files?path=Essai')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['entries'][0]['name'],'été.txt')
        path=quote('Essai/été.txt')
        self.assertEqual(self.request('GET','/api/download?path='+path),(200,payload))
        self.assertEqual(json.loads(self.request('GET','/api/preview?path='+path)[1])['text'],payload.decode())
        self.assertEqual(list((self.root/'Essai').glob('.upload-*')),[])
        self.assertEqual(self.request('POST','/api/upload?name=big',raw=b'x'*1025)[0],413)
        self.assertFalse((self.root/'big').exists())
        self.assertEqual(self.request('POST','/api/upload?name=empty.txt',raw=b'')[0],201)

    def test_confinement_and_static_allowlist(self):
        self.setup_user()
        outside=Path(self.temp.name)/'outside'
        outside.mkdir()
        (outside/'secret.txt').write_text('private')
        (self.root/'escape').symlink_to(outside,target_is_directory=True)
        (self.root/'secret-link').symlink_to(outside/'secret.txt')
        for path in ('../outside','/etc','a/../b','.hidden','a\\b'):
            self.assertEqual(self.request('GET','/api/files?path='+quote(path,safe=''))[0],400)
        for endpoint in ('/api/files?path=escape','/api/download?path=escape/secret.txt','/api/download?path=secret-link'):
            self.assertEqual(self.request('GET',endpoint)[0],403)
        self.assertEqual(self.request('POST','/api/upload?path=escape&name=x',raw=b'x')[0],403)
        self.assertEqual(self.request('POST','/api/upload?name=..%2Fbad',raw=b'x')[0],400)
        for endpoint in ('/server.py','/README.md','/auth.json','/assets/../server.py'):
            self.assertEqual(self.request('GET',endpoint)[0],404)
        self.assertEqual(json.loads(self.request('GET','/api/files')[1])['entries'],[])

    def test_image_preview_auth_content_and_confinement(self):
        payload=Path(__file__).with_name('image-test.png').read_bytes()
        self.assertEqual(self.request('GET','/api/image?path=image.png')[0],401)
        self.setup_user()
        self.assertEqual(self.request('POST','/api/upload?name=image.png',raw=payload)[0],201)
        status,data=self.request('GET','/api/preview?path=image.png')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(data)['mime'],'image/png')
        self.assertEqual(self.request('GET','/api/image?path=image.png'),(200,payload))
        self.assertEqual(self.request('GET','/api/download?path=image.png'),(200,payload))
        self.assertEqual(self.request('GET','/api/image?path=..%2Fsecret')[0],400)
        outside=Path(self.temp.name)/'outside.png'
        outside.write_bytes(payload)
        (self.root/'link.png').symlink_to(outside)
        self.assertEqual(self.request('GET','/api/image?path=link.png')[0],403)
        for name,content in [('fake.jpg',b'<html><script>alert(1)</script></html>'),('fake.png',b'<svg onload="alert(1)"/>')]:
            self.assertEqual(self.request('POST','/api/upload?name='+name,raw=content)[0],201)
            self.assertEqual(self.request('GET','/api/image?path='+name)[0],415)
        self.assertEqual(self.request('POST','/api/upload?name=renamed.bin',raw=payload)[0],201)
        self.assertEqual(json.loads(self.request('GET','/api/preview?path=renamed.bin')[1])['kind'],'image')
        self.assertEqual(self.request('POST','/api/upload?name=test.heic',raw=b'\0\0\0\x18ftypheic')[0],201)
        self.assertEqual(self.request('GET','/api/preview?path=test.heic')[0],415)

    def test_csrf_origin_host_and_rate_limit(self):
        self.assertEqual(self.request('POST','/api/setup',{'user':'test','password':self.password},headers={'Origin':'http://foreign.test'})[0],403)
        self.setup_user()
        for headers in ({'X-CSRF-Token':''},{'Origin':'http://foreign.test'},{'Origin':''},{'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.request('POST','/api/folders',{'name':'blocked'},headers=headers)[0],403)
        self.assertFalse((self.root/'blocked').exists())
        self.assertEqual(self.request('GET','/api/session',headers={'Host':'foreign.test'})[0],403)
        self.request('POST','/api/logout',{})
        self.refresh()
        self.assertEqual(self.request('POST','/api/folders',{'name':'unauthorized'})[0],401)
        for _ in range(4):
            self.assertEqual(self.request('POST','/api/login',{'user':'test','password':'incorrect-password'})[0],401)
        self.assertEqual(self.request('POST','/api/login',{'user':'test','password':self.password})[0],429)

    def test_https_cookie_and_exact_proxy_boundary(self):
        self.refresh()
        cookie = self.response_headers['Set-Cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/'):
            self.assertIn(attribute, cookie)
        self.assertNotIn('Domain=', cookie)
        self.assertEqual(self.response_headers['Strict-Transport-Security'], 'max-age=31536000')
        for headers in (
            {'Host': '127.0.0.1:' + str(self.service.server_port)},
            {'Host': 'localhost'}, {'Host': PUBLIC_HOST + '.evil.test'},
            {'X-Forwarded-Proto': ''}, {'X-Forwarded-Proto': 'http'},
            {'X-Forwarded-Proto': 'https, http'},
            {'X-Forwarded-Host': ''}, {'X-Forwarded-Host': 'evil.test'},
            {'Tailscale-Funnel-Request': '?1'},
            {'Origin': 'https://evil.test'}, {'Origin': 'null'},
            {'Sec-Fetch-Site': 'same-site'},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('GET', '/api/session', headers=headers)[0], 403)
        self.setup_user()
        for origin in ('http://' + PUBLIC_HOST, PUBLIC_ORIGIN + '/',
                       PUBLIC_ORIGIN + '.evil.test', '', 'null'):
            with self.subTest(origin=origin):
                self.assertEqual(self.request('POST', '/api/folders', {'name': 'blocked'},
                                              headers={'Origin': origin})[0], 403)
        self.assertEqual(self.request('POST', '/api/folders', {'name': 'blocked'},
                                     headers={'X-CSRF-Token': '\u00e9'})[0], 403)
        self.assertFalse((self.root / 'blocked').exists())
        self.assertEqual(self.request('POST', '/api/logout', {})[0], 200)
        self.assertIn('Secure', self.response_headers['Set-Cookie'])
        self.assertIn('Max-Age=0', self.response_headers['Set-Cookie'])

    def test_duplicate_security_headers_are_rejected(self):
        for duplicate, value in (('Host', PUBLIC_HOST), ('Origin', PUBLIC_ORIGIN),
                                 ('X-Forwarded-Host', PUBLIC_HOST),
                                 ('X-Forwarded-Proto', 'https'),
                                 ('X-CSRF-Token', self.csrf)):
            with self.subTest(header=duplicate):
                c = http.client.HTTPConnection('127.0.0.1', self.service.server_port, timeout=5)
                c.putrequest('POST', '/api/setup', skip_host=True)
                for k, v in {'Host': PUBLIC_HOST, 'Origin': PUBLIC_ORIGIN,
                             'X-Forwarded-Host': PUBLIC_HOST, 'X-Forwarded-Proto': 'https',
                             'Cookie': self.cookie, 'X-CSRF-Token': self.csrf,
                             'Content-Type': 'application/json', 'Content-Length': '2'}.items():
                    c.putheader(k, v)
                c.putheader(duplicate, value)
                c.endheaders(b'{}')
                r = c.getresponse()
                self.assertEqual(r.status, 403)
                r.read()
                c.close()
        self.assertFalse(self.service.authfile.exists())

    def test_account_files_and_permissions_survive_service_restart(self):
        self.setup_user()
        payload = b'Fichier temporaire a conserver au redemarrage.'
        self.assertEqual(self.request('POST', '/api/upload?name=persist.txt', raw=payload)[0], 201)
        account = self.service.authfile.read_bytes()
        mode = self.root.stat().st_mode & 0o777
        self.service.shutdown()
        self.service.server_close()
        self.thread.join(timeout=5)
        self.service = Service(('127.0.0.1', 0), self.static, self.root, self.state, 1024, family_root=self.family)
        self.thread = threading.Thread(target=self.service.serve_forever, daemon=True)
        self.thread.start()
        self.assertEqual(self.request('GET', '/api/files')[0], 401)
        self.assertFalse(self.refresh()['setup'])
        self.assertEqual(self.request('POST', '/api/login', {'user': 'test', 'password': self.password})[0], 200)
        self.assertEqual(self.request('GET', '/api/download?path=persist.txt'), (200, payload))
        self.assertEqual(self.service.authfile.read_bytes(), account)
        self.assertEqual(self.root.stat().st_mode & 0o777, mode)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)

    def test_non_loopback_binding_is_refused(self):
        with self.assertRaises(ValueError):
            Service(('0.0.0.0', 0), self.static, self.root, self.state, family_root=self.family)

if __name__=='__main__':
    unittest.main(verbosity=2)
