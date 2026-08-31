"""
generate_certs.py — Self-Signed PKI for the FHIPE Demo (Item #7, Day 4)
=========================================================================
Run this script ONCE before starting hospital.py, clinic.py, and cloud.py.

It creates a private Certificate Authority (CA) and issues individual
X.509 certificates for each party, all signed by that CA.  The three
Flask services will use these certs for mutual TLS (mTLS) in Task 5.

Output files (written to the current directory):
    ca.pem              — CA certificate  (public, share with everyone)
    ca-key.pem          — CA private key  (keep secret)
    hospital.pem        — Hospital certificate
    hospital-key.pem    — Hospital private key
    clinic.pem          — Clinic certificate
    clinic-key.pem      — Clinic private key
    cloud.pem           — Cloud certificate
    cloud-key.pem       — Cloud private key

Each certificate includes a SubjectAlternativeName (SAN) extension
covering both 127.0.0.1 and localhost, which is required by modern
Python ssl / requests to pass hostname verification.

Usage:
    python generate_certs.py
"""

import datetime
import ipaddress
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rsa_key() -> rsa.RSAPrivateKey:
    """Generate a 2048-bit RSA private key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _save_key(key: rsa.RSAPrivateKey, path: str) -> None:
    """Write a private key to a PEM file (no passphrase)."""
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(path, "wb") as f:
        f.write(pem)
    print(f"  [wrote] {path}")


def _save_cert(cert: x509.Certificate, path: str) -> None:
    """Write a certificate to a PEM file."""
    pem = cert.public_bytes(serialization.Encoding.PEM)
    with open(path, "wb") as f:
        f.write(pem)
    print(f"  [wrote] {path}")


def _san_extension() -> x509.SubjectAlternativeName:
    """SAN covering 127.0.0.1 and localhost — required for requests/ssl to
    accept the cert without a hostname mismatch error."""
    return x509.SubjectAlternativeName([
        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        x509.DNSName("localhost"),
    ])


# ---------------------------------------------------------------------------
# Step 1: Create the root Certificate Authority
# ---------------------------------------------------------------------------

def create_ca():
    """Generate a root CA key + self-signed certificate."""
    print("\n[1/4] Generating root CA...")
    key = _make_rsa_key()

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FHIPE Demo CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "FHIPE Root CA"),
    ])

    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))   # 10-year CA lifetime
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    _save_key(key, "ca-key.pem")
    _save_cert(cert, "ca.pem")
    return key, cert


# ---------------------------------------------------------------------------
# Step 2: Issue a signed certificate for one party
# ---------------------------------------------------------------------------

def issue_cert(name: str, ca_key, ca_cert: x509.Certificate):
    """Generate a key + certificate for `name`, signed by the CA.

    Args:
        name:     Human-readable name used in the CN and output filenames.
                  e.g. 'hospital', 'clinic', 'cloud'
        ca_key:   The CA's private key (used to sign).
        ca_cert:  The CA's certificate (used as issuer).
    """
    key = _make_rsa_key()

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FHIPE Demo"),
        x509.NameAttribute(NameOID.COMMON_NAME, name.capitalize()),
    ])

    now = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))    # 1-year leaf lifetime
        .add_extension(_san_extension(), critical=False)
        # Mark as end-entity, not a CA
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    _save_key(key,  f"{name}-key.pem")
    _save_cert(cert, f"{name}.pem")
    return key, cert


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  FHIPE Demo — Certificate Generation")
    print("=" * 60)

    # Check if certs already exist — warn before overwriting
    existing = [f for f in ["ca.pem", "hospital.pem", "clinic.pem", "cloud.pem"] if os.path.exists(f)]
    if existing:
        print(f"\n[WARNING] The following cert files already exist and will be overwritten:")
        for f in existing:
            print(f"  {f}")
        answer = input("\nOverwrite? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            exit(0)

    ca_key, ca_cert = create_ca()

    parties = ["hospital", "clinic", "cloud"]
    for party in parties:
        print(f"\n[+] Issuing certificate for: {party}")
        issue_cert(party, ca_key, ca_cert)

    print("\n" + "=" * 60)
    print("  Done! Files written:")
    all_files = ["ca.pem", "ca-key.pem"] + [f"{p}.pem" for p in parties] + [f"{p}-key.pem" for p in parties]
    for f in all_files:
        size = os.path.getsize(f)
        print(f"    {f:<22s}  ({size} bytes)")
    print("=" * 60)
    print("\nNext step: Run Task 5 to enable mTLS on hospital.py, cloud.py,")
    print("           and update requests calls in clinic.py.")
