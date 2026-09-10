"""Key custody — the boundary private keys must never cross.

Two implementations behind one ABC:

  SoftKeyStore   dev and CI. Keys are generated in this process and stored encrypted at rest
                 with the existing Fernet chain (`secrets_box`), so a database dump alone does
                 not yield signing keys. Honest about what it is: a software keystore. Not
                 FIPS, not tamper-resistant, not for production signing.

  Pkcs11KeyStore production. Keys are generated **inside** the HSM with CKA_EXTRACTABLE=false
                 and CKA_SENSITIVE=true, and never leave it. This module only ever holds a
                 handle. Works against SoftHSM2 (so the code path is exercised in CI) and
                 against a FIPS 140-2 Level 3 device in production — see the compatibility
                 note in docs/PKI-ARCHITECTURE.md for Thales Luna / Utimaco / Entrust nShield.

The seam exists because the RFP requires HSM-protected keys at FIPS 140-2 Level 3, and CI
cannot have one. Making the *interface* the tested thing — with SoftHSM2 proving the PKCS#11
path really does keep keys inside the token — is the honest way to build that.

`KEYSTORE_PROVIDER=pkcs11` activates the HSM path; it requires `requirements-pki.txt`
(`python-pkcs11`) plus `HSM_LIBRARY_PATH`, `HSM_SLOT` (or `HSM_TOKEN_LABEL`) and `HSM_PIN`.
The PIN comes from the environment or a secret store — never a file in the repository.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from ..config import settings

log = logging.getLogger("uvicorn.error")


class KeyStoreError(RuntimeError):
    """Raised when key material cannot be created, found or used."""


@dataclass(frozen=True)
class KeySpec:
    """Algorithm choice, expressed the way the config and the DB rows spell it."""

    name: str  # ec-p256 | ec-p384 | rsa-2048 | rsa-3072 | rsa-4096

    @property
    def is_ec(self) -> bool:
        return self.name.startswith("ec-")

    @property
    def curve(self) -> ec.EllipticCurve:
        return {"ec-p256": ec.SECP256R1(), "ec-p384": ec.SECP384R1(), "ec-p521": ec.SECP521R1()}[self.name]

    @property
    def rsa_bits(self) -> int:
        return {"rsa-2048": 2048, "rsa-3072": 3072, "rsa-4096": 4096}[self.name]


SUPPORTED = ("ec-p256", "ec-p384", "ec-p521", "rsa-2048", "rsa-3072", "rsa-4096")


class KeyStore(ABC):
    """Generate, use and destroy private keys without ever exposing them to callers.

    Note there is no `export_private_key`. That is the point: a caller cannot accidentally
    (or maliciously) serialise a key out of the store, so the HSM and software paths have the
    same capability surface and code written against one works against the other.

    Every method takes the caller's `db` session. That is not incidental: the software
    keystore persists key material in `pki_keys`, and generating a key must happen **in the
    same transaction** as writing the CA or certificate row that references it. A keystore
    holding its own session deadlocks on SQLite, and on any engine leaves orphaned key
    material behind when the caller rolls back. The PKCS#11 store ignores the session — its
    keys live in the token — but keeps the parameter so both paths share one signature.
    """

    name: str

    @abstractmethod
    def generate_keypair(self, db, key_id: str, spec: KeySpec) -> str:
        """Create a keypair under `key_id`. Returns the handle to persist on the row."""

    @abstractmethod
    def sign(self, db, key_id: str, data: bytes, *, hash_alg: str = "sha256") -> bytes:
        """Sign `data`. ECDSA yields a DER signature; RSA yields PKCS#1 v1.5."""

    @abstractmethod
    def public_key(self, db, key_id: str):  # -> PublicKeyTypes
        """The public half, as a `cryptography` public key object."""

    @abstractmethod
    def destroy(self, db, key_id: str) -> None:
        """Irreversibly remove the key. Used by the root-CA offlining ceremony."""

    @abstractmethod
    def exists(self, db, key_id: str) -> bool: ...

    def signer_for(self, db, key_id: str):
        """A `cryptography`-compatible private key object for x509 builders.

        Software keystores can hand back the real key. The PKCS#11 store cannot — it returns
        a proxy that forwards `sign()` into the token (see `_Pkcs11PrivateKeyProxy`).
        """
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# Software keystore (dev / CI)
# --------------------------------------------------------------------------------------


class SoftKeyStore(KeyStore):
    """Keys encrypted at rest in the `pki_keys` table via the Fernet chain.

    Kept in its own tiny table rather than a column on `certificates` so that dumping the
    certificate register — the thing an auditor or an admin UI reads — never touches key
    material at all.
    """

    name = "soft"

    def generate_keypair(self, db, key_id: str, spec: KeySpec) -> str:
        from .. import models

        if spec.is_ec:
            key = ec.generate_private_key(spec.curve)
        else:
            key = rsa.generate_private_key(public_exponent=65537, key_size=spec.rsa_bits)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("ascii")

        if db.get(models.PkiKey, key_id) is not None:
            raise KeyStoreError(f"key {key_id} already exists")
        # `material` is an EncryptedString column — the PEM is never written in the clear.
        # Flushed, not committed: the caller owns the transaction.
        db.add(models.PkiKey(id=key_id, algorithm=spec.name, material=pem, provider=self.name))
        db.flush()
        return key_id

    def _load(self, db, key_id: str):  # type: ignore[no-untyped-def]
        from .. import models

        row = db.get(models.PkiKey, key_id)
        if row is None or not row.material:
            raise KeyStoreError(f"key {key_id} not found")
        return serialization.load_pem_private_key(row.material.encode("ascii"), password=None)

    def signer_for(self, db, key_id: str):
        return self._load(db, key_id)

    def sign(self, db, key_id: str, data: bytes, *, hash_alg: str = "sha256") -> bytes:
        key = self._load(db, key_id)
        algo = {"sha256": hashes.SHA256(), "sha384": hashes.SHA384(), "sha512": hashes.SHA512()}[hash_alg]
        if isinstance(key, ec.EllipticCurvePrivateKey):
            return key.sign(data, ec.ECDSA(algo))
        return key.sign(data, padding.PKCS1v15(), algo)

    def public_key(self, db, key_id: str):
        return self._load(db, key_id).public_key()

    def exists(self, db, key_id: str) -> bool:
        from .. import models

        return db.get(models.PkiKey, key_id) is not None

    def destroy(self, db, key_id: str) -> None:
        from .. import models

        row = db.get(models.PkiKey, key_id)
        if row is not None:
            db.delete(row)
            db.flush()


# --------------------------------------------------------------------------------------
# PKCS#11 keystore (production HSM)
# --------------------------------------------------------------------------------------


class _Pkcs11PrivateKeyProxy:
    """Quacks like a `cryptography` private key so `x509.CertificateBuilder.sign()` works,
    but every signature is computed inside the token.

    `cryptography` calls `.sign(data, ...)` on whatever it is handed and needs `.public_key()`
    plus a `.curve` / `.key_size` attribute to pick the signature encoding. That is the whole
    contract, so a proxy is enough — and it means `ca.py` has one code path for software and
    HSM keys instead of two.
    """

    def __init__(self, store: Pkcs11KeyStore, key_id: str) -> None:
        self._store = store
        self._key_id = key_id
        self._public = store.public_key(None, key_id)

    def public_key(self):
        return self._public

    @property
    def curve(self):
        return getattr(self._public, "curve", None)

    @property
    def key_size(self):
        return getattr(self._public, "key_size", None)

    def sign(self, data: bytes, *args, **kwargs) -> bytes:  # noqa: ARG002
        hash_alg = "sha256"
        for a in args:
            algo = getattr(a, "algorithm", a)
            name = getattr(algo, "name", "")
            if name in ("sha256", "sha384", "sha512"):
                hash_alg = name
        return self._store.sign(None, self._key_id, data, hash_alg=hash_alg)


class Pkcs11KeyStore(KeyStore):
    """Keys generated inside, and confined to, a PKCS#11 token.

    Generation sets CKA_SENSITIVE=true and CKA_EXTRACTABLE=false, which is what makes
    "the private key never leaves the HSM" a property of the token rather than a promise
    from this code. `destroy()` removes the object from the token; there is no export path.
    """

    name = "pkcs11"

    def __init__(self) -> None:
        try:
            import pkcs11  # noqa: F401
        except ImportError as e:  # pragma: no cover - exercised only without the extra
            raise KeyStoreError(
                "KEYSTORE_PROVIDER=pkcs11 requires python-pkcs11 — pip install -r requirements-pki.txt"
            ) from e
        if not settings.hsm_library_path:
            raise KeyStoreError("HSM_LIBRARY_PATH is not set.")
        self._token = None

    def _open(self):  # type: ignore[no-untyped-def]
        """A logged-in session. Opened lazily and per-call: PKCS#11 sessions are not
        thread-safe, and this process is threaded under uvicorn."""
        import pkcs11

        lib = pkcs11.lib(settings.hsm_library_path)
        if settings.hsm_token_label:
            token = lib.get_token(token_label=settings.hsm_token_label)
        else:
            token = lib.get_token(slot_id=settings.hsm_slot)
        return token.open(rw=True, user_pin=settings.hsm_pin)

    def generate_keypair(self, db, key_id: str, spec: KeySpec) -> str:  # noqa: ARG002 - key lives in the token
        from pkcs11 import Attribute, KeyType, ObjectClass
        from pkcs11.util.ec import encode_named_curve_parameters

        with self._open() as session:
            existing = list(session.get_objects({
                Attribute.CLASS: ObjectClass.PRIVATE_KEY, Attribute.LABEL: key_id,
            }))
            if existing:
                raise KeyStoreError(f"key {key_id} already exists in the token")

            private_template = {
                Attribute.TOKEN: True,        # persist in the token, not the session
                Attribute.PRIVATE: True,
                Attribute.SENSITIVE: True,    # value cannot be read back
                Attribute.EXTRACTABLE: False,  # and cannot be wrapped out either
                Attribute.SIGN: True,
                Attribute.LABEL: key_id,
            }
            public_template = {Attribute.TOKEN: True, Attribute.VERIFY: True, Attribute.LABEL: key_id}

            if spec.is_ec:
                curve = {"ec-p256": "secp256r1", "ec-p384": "secp384r1", "ec-p521": "secp521r1"}[spec.name]
                public_template[Attribute.EC_PARAMS] = encode_named_curve_parameters(curve)
                session.generate_keypair(
                    KeyType.EC, store=True,
                    private_template=private_template, public_template=public_template,
                )
            else:
                session.generate_keypair(
                    KeyType.RSA, spec.rsa_bits, store=True,
                    private_template=private_template, public_template=public_template,
                )
        log.info("pkcs11: generated %s keypair %r inside the token", spec.name, key_id)
        return key_id

    def _find(self, session, key_id: str, object_class):  # type: ignore[no-untyped-def]
        from pkcs11 import Attribute

        found = list(session.get_objects({Attribute.CLASS: object_class, Attribute.LABEL: key_id}))
        if not found:
            raise KeyStoreError(f"key {key_id} not found in the token")
        return found[0]

    def sign(self, db, key_id: str, data: bytes, *, hash_alg: str = "sha256") -> bytes:  # noqa: ARG002
        from pkcs11 import Mechanism, ObjectClass
        from pkcs11.util.ec import encode_ecdsa_signature

        mechanisms = {
            ("ec", "sha256"): Mechanism.ECDSA_SHA256,
            ("ec", "sha384"): Mechanism.ECDSA_SHA384,
            ("ec", "sha512"): Mechanism.ECDSA_SHA512,
            ("rsa", "sha256"): Mechanism.SHA256_RSA_PKCS,
            ("rsa", "sha384"): Mechanism.SHA384_RSA_PKCS,
            ("rsa", "sha512"): Mechanism.SHA512_RSA_PKCS,
        }
        with self._open() as session:
            key = self._find(session, key_id, ObjectClass.PRIVATE_KEY)
            kind = "ec" if "EC" in str(key.key_type) else "rsa"
            sig = key.sign(data, mechanism=mechanisms[(kind, hash_alg)])
            # PKCS#11 returns raw r||s for ECDSA; X.509 wants DER.
            return encode_ecdsa_signature(sig) if kind == "ec" else bytes(sig)

    def public_key(self, db, key_id: str):  # noqa: ARG002
        from pkcs11 import ObjectClass
        from pkcs11.util.ec import encode_ec_public_key
        from pkcs11.util.rsa import encode_rsa_public_key

        with self._open() as session:
            key = self._find(session, key_id, ObjectClass.PUBLIC_KEY)
            kind = "ec" if "EC" in str(key.key_type) else "rsa"
            der = encode_ec_public_key(key) if kind == "ec" else encode_rsa_public_key(key)
        return serialization.load_der_public_key(der)

    def signer_for(self, db, key_id: str):  # noqa: ARG002
        return _Pkcs11PrivateKeyProxy(self, key_id)

    def exists(self, db, key_id: str) -> bool:  # noqa: ARG002
        from pkcs11 import ObjectClass

        try:
            with self._open() as session:
                self._find(session, key_id, ObjectClass.PRIVATE_KEY)
            return True
        except KeyStoreError:
            return False

    def destroy(self, db, key_id: str) -> None:  # noqa: ARG002
        from pkcs11 import Attribute, ObjectClass

        with self._open() as session:
            for cls in (ObjectClass.PRIVATE_KEY, ObjectClass.PUBLIC_KEY):
                for obj in session.get_objects({Attribute.CLASS: cls, Attribute.LABEL: key_id}):
                    obj.destroy()


# --------------------------------------------------------------------------------------


_store: KeyStore | None = None


def get_keystore() -> KeyStore:
    global _store
    if _store is None:
        _store = Pkcs11KeyStore() if settings.keystore_provider == "pkcs11" else SoftKeyStore()
        if settings.keystore_provider != "pkcs11" and settings.is_production:
            log.warning(
                "PKI is using the SOFTWARE keystore in a production environment. "
                "Signing keys are encrypted at rest but are not HSM-protected. "
                "Set KEYSTORE_PROVIDER=pkcs11 for a FIPS 140-2 deployment."
            )
    return _store


def reset_keystore() -> None:
    """Drop the cached instance. Tests switch providers; nothing else should call this."""
    global _store
    _store = None
