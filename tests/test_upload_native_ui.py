import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import struct
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import upload_native_ui as subject
from switch_transport import SwitchError


class ImageAssetTests(unittest.TestCase):
    def fixture(self):
        image=bytearray(20+0x2d6000)
        html=b'<meta name="mxl-transport" content="native">Hello'
        for off,value in [(0x15f72,len(html)),(0x1600e,len(html)),(0x15f78,0x4026a000),(0x16014,0x4026a000)]:
            struct.pack_into('<HH',image,20+off,value >> 16,value & 65535)
        image[20+0x26a000:20+0x26a000+len(html)]=html
        return image,html

    def test_digest_comes_from_actual_payload(self):
        image,html=self.fixture()
        self.assertEqual(subject.expected_ui_digest(image),hashlib.sha256(html).hexdigest())

    def test_large_asset_within_reserved_padding_is_accepted(self):
        image,html=self.fixture()
        html=html.ljust(210000,b' ')
        for offset in (0x15f72,0x1600e):
            struct.pack_into('<HH',image,20+offset,len(html) >> 16,len(html) & 65535)
        image[20+0x26a000:20+0x26a000+len(html)]=html
        self.assertEqual(subject.expected_ui_digest(image),hashlib.sha256(html).hexdigest())

    def test_mismatched_pointer_length_and_asset_rejected(self):
        for off in [0x15f72,0x1600e,0x15f78,0x16014,0x26a000]:
            image,_=self.fixture();image[20+off]^=1
            with self.subTest(offset=off),self.assertRaises(ValueError):subject.expected_ui_digest(image)


class ServedUiTests(unittest.TestCase):
    def test_unavailable_then_old_then_exact_asset(self):
        class Transport:
            def __init__(self):self.calls=[]
            def request(self,path,**kwargs):
                self.calls.append((path,kwargs))
                if len(self.calls)==1:raise SwitchError('Temporarily unavailable')
                return {'bytes':b'old' if len(self.calls)==2 else b'new'}
        transport=Transport()
        result=subject.verify_served_ui(transport,hashlib.sha256(b'new').hexdigest(),interval=0)
        self.assertTrue(result['matched']);self.assertEqual(result['attempts'],3)
        self.assertFalse(result['uart_boot_verified']);self.assertFalse(result['forwarding_verified'])
        self.assertEqual(transport.calls,[('/login.html',{'binary':True,'authenticate':False})]*3)

    def test_timeout_records_mismatch_without_any_write_retry(self):
        class Transport:
            def request(self,path,**kwargs):return {'bytes':b'old'}
        with patch.object(subject.time,'monotonic',side_effect=[0,0,1,3]):
            result=subject.verify_served_ui(Transport(),'expected',timeout=2,interval=0)
        self.assertFalse(result['matched']);self.assertEqual(result['attempts'],1)
        self.assertEqual(result['last_observed_ui_sha256'],hashlib.sha256(b'old').hexdigest())


class ChunkClientTests(unittest.TestCase):
    def test_sequential_raw_posts_and_server_requested_connection_close(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args):pass
            def do_POST(self):
                seen.append((self.path,self.headers['Cookie'],
                             self.headers['Content-Type'],
                             self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.send_header('Content-Length','2')
                self.send_header('Connection','close')
                self.end_headers();self.wfile.write(b'OK')
                self.close_connection=True
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        client=subject.ChunkClient('127.0.0.1', 'session=test')
        client.connection.port=server.server_port
        try:
            for payload in (b'\0'*41000,b'final'):
                result=client.post(payload,2)
                self.assertEqual(result['http_status'],200)
                self.assertIsNone(result['transport_error'])
                self.assertEqual(result['response'],'OK')
            self.assertEqual(seen,[('/firmware/upgrade','session=test',
                                   'application/octet-stream',p)
                                  for p in (b'\0'*41000,b'final')])
        finally:
            client.close();server.shutdown();server.server_close();worker.join()

    def test_lost_reply_is_not_replayed_or_reported_as_success(self):
        with patch.object(subject.http.client,'HTTPConnection') as constructor:
            connection=constructor.return_value
            connection.getresponse.side_effect=http.client.RemoteDisconnected('lost reply')
            result=subject.ChunkClient('192.0.2.1','session=private').post(b'one',2)
            self.assertEqual(connection.request.call_count,1)
            self.assertEqual(connection.close.call_count,1)
            self.assertIsNone(result['http_status'])
            self.assertEqual(result['transport_error'],'RemoteDisconnected')
            self.assertNotIn('private',str(result))


if __name__=='__main__':unittest.main()
