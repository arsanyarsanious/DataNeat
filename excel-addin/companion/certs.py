"""Generate and trust the localhost certificate used by the Excel add-in.

The task pane and the local DataNeat engine share one HTTPS origin so Office.js
can call the engine without mixed-content or CORS problems. The certificate is
kept under excel-addin/companion/certs (ignored by git) and trusted only for the
current Windows user.
"""
import ipaddress
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def generate():
    certs = Path(__file__).resolve().parent / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    cert_path = certs / "cert.pem"
    key_path = certs / "key.pem"
    if cert_path.exists() and key_path.exists():
        print(f"Certificate already exists: {cert_path}")
        return cert_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"Created {cert_path} and {key_path}")
    return cert_path


def trust(cert_path):
    if sys.platform != "win32":
        print("Trust the certificate manually in your browser/OS trust store.")
        return
    result = subprocess.run(
        ["certutil", "-addstore", "-user", "Root", str(cert_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Trusted the localhost certificate for the current Windows user.")
    else:
        print("Could not add the certificate automatically. Run this as your user:")
        print(f'  certutil -addstore -user Root "{cert_path}"')
        print(result.stdout.strip() or result.stderr.strip())


if __name__ == "__main__":
    trust(generate())
