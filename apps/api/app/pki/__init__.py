"""In-platform Public Key Infrastructure.

Built on cryptographic **primitives** (`cryptography`), not by wrapping an existing CA
product. That is a deliberate constraint, not an aesthetic one: the RFP requires a sworn
undertaking that the PKI and eSignature engine is the bidder's own proprietary, in-house
engineered work — not open source and not a derivative. Primitive libraries are expected in
the SBOM; a wrapped EJBCA / Dogtag / step-ca would break the undertaking.

Module map:

    keystore.py   key custody seam — SoftKeyStore (dev/CI) and Pkcs11KeyStore (HSM)
    ca.py         CA hierarchy — offline root, online issuing CA, cross-certification
    ra.py         Registration Authority workflow — nothing is issued without an approval
    lifecycle.py  enrol / issue / renew / suspend / resume / revoke
    crl.py        full and delta Certificate Revocation Lists
    ocsp.py       RFC 6960 responder
    validate.py   RFC 5280 path validation for third-party certificates

See docs/PKI-ARCHITECTURE.md for the hierarchy, key ceremony, HSM model and the ECAC
chaining plan.
"""
