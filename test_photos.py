import json
import os
from pathlib import Path
import unittest
from urllib.parse import quote
import test_server as base
import test_family as family


class PhotoTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh
    setup_user = base.ServiceTests.setup_user
    create = family.FamilyTests.create
    login = family.FamilyTests.login
    restart = family.FamilyTests.restart

    def gallery(self, space='private'):
        status, raw = self.request('GET', '/api/photos?space='+space)
        self.assertEqual(status, 200, raw)
        return json.loads(raw)

    def upload(self, name='image.png', space='private'):
        status, _ = self.request('POST', '/api/folders?space='+space, {'name': 'Photos'})
        self.assertIn(status, (201, 409))
        image = Path(__file__).with_name('image-test.png').read_bytes()
        self.assertEqual(self.request('POST', '/api/upload?space='+space+'&path=Photos&name='+quote(name), raw=image)[0], 201)
        return image

    def test_auth_missing_directory_is_read_only_and_no_cache(self):
        self.assertEqual(self.request('GET', '/api/photos')[0], 401)
        self.setup_user()
        for space in ('private', 'shared'):
            self.assertEqual(self.gallery(space), {'entries': [], 'ignored': 0, 'exists': False})
            self.assertIn('no-store', self.response_headers['Cache-Control'])
        self.assertFalse((self.root/'Photos').exists())
        self.assertFalse((self.family/'shared'/'Photos').exists())
        self.assertEqual(self.request('GET', '/api/photos', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/photos', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/photos', headers={'Tailscale-Funnel-Request': '1'})[0], 403)

    def test_owner_and_two_members_private_shared_and_restart(self):
        self.setup_user();self.create('Alice');self.create('Bob')
        for name in ('test', 'Alice', 'Bob'):
            self.login(name)
            self.assertEqual(self.gallery()['entries'], [])
            self.upload(name+'.png')
        self.upload('famille.png', 'shared')
        self.restart()
        for name in ('test', 'Alice', 'Bob'):
            self.login(name)
            self.assertEqual([p['name'] for p in self.gallery()['entries']], [name+'.png'])
            self.assertEqual([p['name'] for p in self.gallery('shared')['entries']], ['famille.png'])
            other = 'Alice' if name == 'test' else 'test'
            self.assertEqual(self.request('GET', '/api/image?path=Photos/'+other+'.png')[0], 404)

    def test_bytes_collision_and_files_use_same_original(self):
        self.setup_user();image=self.upload('été & soleil.png')
        path = quote('Photos/été & soleil.png')
        self.assertEqual(self.request('GET', '/api/download?path='+path), (200, image))
        self.assertEqual(self.request('GET', '/api/image?path='+path), (200, image))
        self.assertEqual(self.response_headers['Content-Type'], 'image/png')
        self.assertEqual(json.loads(self.request('GET', '/api/files?path=Photos')[1])['entries'][0]['name'], 'été & soleil.png')
        self.assertEqual(self.request('POST', '/api/upload?path=Photos&name='+quote('été & soleil.png'), raw=b'changed')[0], 409)
        self.assertEqual((self.root/'Photos'/'été & soleil.png').read_bytes(), image)
        self.assertEqual((self.root/'Photos'/'été & soleil.png').stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(list((self.root/'Photos').iterdir())), 1)

    def test_signatures_filter_formats_and_sort_without_recursion(self):
        self.setup_user();directory=self.root/'Photos';directory.mkdir()
        payloads={'jpeg.bin':b'\xff\xd8\xfftest','png.bin':b'\x89PNG\r\n\x1a\ntest',
                  'gif.bin':b'GIF89atest','webp.bin':b'RIFF1234WEBPtest',
                  'fake.jpg':b'<svg></svg>','phone.heic':b'1234ftypheic','raw.nef':b'RAW', '.hidden.png':b'\xff\xd8\xff'}
        for index,(name,data) in enumerate(payloads.items()):
            (directory/name).write_bytes(data);os.utime(directory/name,(100+index,100+index))
        (directory/'Album').mkdir();(directory/'Album'/'nested.png').write_bytes(b'\xff\xd8\xff')
        data=self.gallery()
        self.assertEqual([p['name'] for p in data['entries']], ['webp.bin','gif.bin','png.bin','jpeg.bin'])
        self.assertEqual([p['mime'] for p in data['entries']], ['image/webp','image/gif','image/png','image/jpeg'])
        self.assertEqual(data['ignored'], 5)
        self.assertEqual(self.request('GET', '/api/image?path=Photos/fake.jpg')[0], 415)

    def test_links_special_files_and_conflicting_photos_path(self):
        self.setup_user();outside=self.state/'secret.png';outside.write_bytes(b'\xff\xd8\xffsecret')
        directory=self.root/'Photos';directory.symlink_to(self.state, target_is_directory=True)
        self.assertEqual(self.request('GET', '/api/photos')[0], 403)
        directory.unlink();directory.write_text('keep')
        self.assertEqual(self.request('GET', '/api/photos')[0], 403)
        self.assertEqual(directory.read_text(), 'keep')
        directory.unlink();directory.mkdir()
        (directory/'secret.png').symlink_to(outside)
        os.mkfifo(directory/'pipe.png')
        self.assertEqual(self.gallery()['entries'], [])
        self.assertEqual(self.request('GET', '/api/image?path=Photos/secret.png')[0], 403)

    def test_query_cannot_select_account_path_or_repeat_space(self):
        self.setup_user()
        for query in ('path=Photos','path=../','name=hello','space=other','space=private&space=shared','accountId=abc','root=/tmp'):
            self.assertEqual(self.request('GET', '/api/photos?'+query)[0], 400)

    def test_scan_is_bounded_even_for_unsupported_files(self):
        self.setup_user();directory=self.root/'Photos';directory.mkdir()
        for index in range(2001):
            (directory/str(index)).touch()
        self.assertEqual(self.request('GET', '/api/photos')[0], 413)

    def test_disabled_member_loses_gallery_and_image_access(self):
        self.setup_user();member=self.create('Alice');self.upload('famille.png','shared')
        owner_cookie,owner_csrf=self.cookie,self.csrf
        self.login('Alice');self.gallery('shared')
        member_cookie,member_csrf=self.cookie,self.csrf
        self.cookie,self.csrf=owner_cookie,owner_csrf
        self.assertEqual(self.request('POST','/api/accounts/status',{'id':member['id'],'active':False})[0],200)
        self.cookie,self.csrf=member_cookie,member_csrf
        self.assertEqual(self.request('GET','/api/photos?space=shared')[0],401)
        self.assertEqual(self.request('GET','/api/image?space=shared&path=Photos/famille.png')[0],401)
