"""Verify APNs requests against an in-process transport, never Apple's servers."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from push_worker import APNsTransport


class APNsTransportTests(unittest.TestCase):
    def test_signed_http2_request_and_environment(self):
        key=ec.generate_private_key(ec.SECP256R1())
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        calls=[]
        def handle(request):
            calls.append(request)
            return httpx.Response(200)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test-key.p8';path.write_bytes(pem)
            client=httpx.Client(transport=httpx.MockTransport(handle))
            with patch.dict(os.environ,{'APNS_TEAM_ID':'TESTTEAM','APNS_KEY_ID':'TESTKEY','APNS_TOPIC':'com.test.order','APNS_KEY_PATH':str(path)}), patch('httpx.Client',return_value=client):
                transport=APNsTransport()
            row=SimpleNamespace(id=2,message_id=8)
            device=SimpleNamespace(environment='sandbox',token='ab'*32)
            self.assertEqual(transport.send(device,row,{'aps':{'alert':'test'}}),(200,''))
            device.environment='production'
            transport.send(device,row,{'aps':{'alert':'test'}})
            self.assertEqual(calls[0].url.host,'api.sandbox.push.apple.com')
            self.assertEqual(calls[1].url.host,'api.push.apple.com')
            headers=calls[0].headers
            self.assertEqual(headers['apns-topic'],'com.test.order')
            self.assertEqual(headers['apns-push-type'],'alert')
            self.assertEqual(headers['apns-collapse-id'],'message-8')
            self.assertEqual(headers['apns-id'],calls[1].headers['apns-id'])
            token=headers['authorization'].removeprefix('bearer ')
            self.assertEqual(jwt.get_unverified_header(token)['kid'],'TESTKEY')
            self.assertEqual(jwt.decode(token,key.public_key(),algorithms=['ES256'])['iss'],'TESTTEAM')
            client.close()

    def test_apple_error_response_is_retained(self):
        transport=APNsTransport.__new__(APNsTransport)
        transport.topic='com.test.order';transport.jwt='fake';transport.issued=10**12
        transport.client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(410,json={'reason':'Unregistered'})))
        result=transport.send(SimpleNamespace(environment='production',token='ab'*32),SimpleNamespace(id=1,message_id=1),{})
        self.assertEqual(result,(410,'Unregistered'))
        transport.client.close()

if __name__=='__main__': unittest.main()
