import json
import os
import unittest
from urllib.parse import quote
import test_server as base
from server import media_type

MP3 = b'ID3\x04\x00\x00\x00\x00\x00\x00' + bytes(range(256)) * 3
MP4 = b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom' + bytes(range(200)) * 4
WAV = b'RIFF\x24\x00\x00\x00WAVEfmt ' + b'\x00' * 300


class MediaTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh
    setup_user = base.ServiceTests.setup_user

    def upload(self, name, data, space='private'):
        status, body = self.request('POST', f'/api/upload?space={space}&name=' + quote(name), raw=data)
        self.assertEqual(status, 201, body)

    def media(self, name, headers=None, method='GET', space='private'):
        return self.request(method, f'/api/media?space={space}&path=' + quote(name), headers=headers)

    def test_signature_and_extension_must_agree(self):
        self.assertEqual(media_type('son.mp3', MP3[:32]), 'audio/mpeg')
        self.assertEqual(media_type('clip.MOV', MP4[:32]), 'video/quicktime')
        self.assertEqual(media_type('note.wav', WAV[:32]), 'audio/wav')
        self.assertIsNone(media_type('faux.mp3', b'hello world, not audio'.ljust(32)))
        self.assertIsNone(media_type('photo.heic', MP4[:32]))      # HEIC reste une photo
        self.assertIsNone(media_type('video.mkv', MP4[:32]))
        self.assertIsNone(media_type('court.mp4', b'\x00' * 4))

    def test_preview_kind_full_and_ranges(self):
        self.assertEqual(self.media('son.mp3')[0], 401)
        self.setup_user()
        self.upload('son.mp3', MP3); self.upload('clip.mp4', MP4); self.upload('note.wav', WAV)
        for name, kind in (('son.mp3', 'audio'), ('clip.mp4', 'video'), ('note.wav', 'audio')):
            status, body = self.request('GET', '/api/preview?space=private&path=' + quote(name))
            self.assertEqual((status, json.loads(body)['kind']), (200, kind), body)
        status, body = self.media('clip.mp4')
        self.assertEqual((status, body), (200, MP4))
        self.assertEqual(self.response_headers['Content-Type'], 'video/mp4')
        self.assertEqual(self.response_headers['Accept-Ranges'], 'bytes')
        self.assertEqual(self.response_headers['Cache-Control'], 'no-store')
        self.assertTrue(self.response_headers['Content-Disposition'].startswith('inline'))
        status, body = self.media('clip.mp4', {'Range': 'bytes=10-19'})
        self.assertEqual((status, body), (206, MP4[10:20]))
        self.assertEqual(self.response_headers['Content-Range'], f'bytes 10-19/{len(MP4)}')
        self.assertEqual(self.media('son.mp3', {'Range': 'bytes=1000-'})[1], MP3[1000:])
        self.assertEqual(self.media('son.mp3', {'Range': 'bytes=-7'})[1], MP3[-7:])
        self.assertEqual(self.media('son.mp3', {'Range': 'bytes=0-999999'})[1], MP3)
        for bad in ('bytes=99999-', 'bytes=5-2', 'items=0-1', 'bytes=0-1,4-5', 'bytes=-0'):
            status, _ = self.media('son.mp3', {'Range': bad})
            self.assertEqual(status, 416, bad)
            self.assertEqual(self.response_headers['Content-Range'], f'bytes */{len(MP3)}')

    def test_refuses_non_media_and_respects_spaces(self):
        self.setup_user()
        self.upload('faux.mp3', b'pas du son du tout, juste du texte')
        self.upload('texte.txt', b'bonjour')
        self.assertEqual(self.media('faux.mp3')[0], 415)
        self.assertEqual(self.media('texte.txt')[0], 415)
        self.assertEqual(self.media('absent.mp3')[0], 404)
        self.assertEqual(self.media('../x.mp3')[0], 400)
        self.upload('famille.mp3', MP3, space='shared')
        self.assertEqual(self.media('famille.mp3', space='shared')[1], MP3)
        self.assertEqual(self.media('famille.mp3')[0], 404)       # pas dans l'espace privé
        root = self.service.root
        os.symlink(os.path.join(root, 'faux.mp3'), os.path.join(root, 'lien.mp3'))
        self.assertIn(self.media('lien.mp3')[0], (403, 404))
        status, body = self.request('GET', '/api/preview?space=private&path=' + quote('photo.heic'))
        self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main()
