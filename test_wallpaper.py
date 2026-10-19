import unittest
import test_server as base


class WallpaperTests(unittest.TestCase):
    setUp = base.ServiceTests.setUp
    tearDown = base.ServiceTests.tearDown
    request = base.ServiceTests.request
    refresh = base.ServiceTests.refresh

    def media(self):
        (self.static/'assets').mkdir()
        data = bytes(range(256)) * 600
        (self.static/'assets/wallpaper.mp4').write_bytes(data)
        return data

    def test_range_streaming_and_head(self):
        data = self.media()
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4'), (200, data))
        self.assertEqual(self.response_headers['Cache-Control'], 'private, max-age=3600')
        for requested, expected in [('bytes=0-1', data[:2]), ('bytes=65530-65540', data[65530:65541]),
                                    ('bytes=-12', data[-12:]), ('bytes=153598-', data[-2:]),
                                    ('bytes=153598-999999', data[-2:])]:
            self.assertEqual(self.request('GET', '/assets/wallpaper.mp4', headers={'Range': requested}), (206, expected))
            self.assertIn('Content-Range', self.response_headers)
        self.assertEqual(self.request('HEAD', '/assets/wallpaper.mp4', headers={'Range': 'bytes=0-1'}), (200, b''))
        self.assertEqual(int(self.response_headers['Content-Length']), len(data))
        self.assertNotIn('Content-Range', self.response_headers)

    def test_invalid_ranges_and_empty_media(self):
        self.media()
        for requested in ('bytes=-0', 'bytes=-', 'bytes=4-2', 'bytes=999999-',
                          'bytes=0-1,4-5', 'bytes=--2', 'items=0-1', 'bytes=1-NaN', 'bytes='+'9'*200+'-'):
            self.assertEqual(self.request('GET', '/assets/wallpaper.mp4', headers={'Range': requested}), (416, b''))
        (self.static/'assets/wallpaper.mp4').write_bytes(b'')
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4'), (200, b''))
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4', headers={'Range': 'bytes=0-'}), (416, b''))

    def test_missing_media_guards_and_no_file_leak(self):
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4')[0], 404)
        self.assertEqual(self.request('HEAD', '/assets/wallpaper.mp4')[0], 404)
        self.assertEqual(self.request('HEAD', '/api/storage')[0], 405)
        self.media()
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4', headers={'X-Forwarded-Proto': 'http'})[0], 403)
        self.assertEqual(self.request('HEAD', '/assets/wallpaper.mp4', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4', headers={'Tailscale-Funnel-Request': 'true'})[0], 403)
        media = self.static/'assets/wallpaper.mp4'
        media.unlink()
        media.symlink_to(self.state/'accounts.json')
        self.assertEqual(self.request('GET', '/assets/wallpaper.mp4')[0], 403)


if __name__ == '__main__':
    unittest.main()
