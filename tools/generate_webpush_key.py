"""Generate a server-only VAPID key without sending data to any service."""
import os
import argparse
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('path', help='New private PEM file; refuses to overwrite an existing key')
    args = parser.parse_args()
    key = ec.generate_private_key(ec.SECP256R1())
    data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as file:
        file.write(data)
    print('Private key generated. Keep it on the server; do not upload it to chat or source control.')
