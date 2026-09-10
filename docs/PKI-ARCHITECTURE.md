# PKI Architecture

**Scope:** the in-platform Public Key Infrastructure that issues, manages and revokes the
signing certificates used by the E-Contract platform.
**Status:** implemented (Phase 1). Code lives in [`apps/api/app/pki/`](../apps/api/app/pki/).
**Audience:** MMBL evaluation committee, the bank's InfoSec function, and the engineers who
will operate this.

This document is the deliverable referenced by RFP §4a *PKI Depth & Advanced eSignature* and
by the §9 Annexure item "PKI architecture document". It is written to be checkable: every
claim points at the code or the test that proves it, and the things that are **not** yet
proven are stated as such in [§10](#10-known-limits).

---

## 1. Design constraint: primitives, not a wrapped CA

MMBL requires a sworn undertaking that the PKI and eSignature engine is the bidder's own
proprietary, in-house engineered work — not open source and not a derivative — backed by an
SBOM.

This CA is therefore built directly on **cryptographic primitives**: the `cryptography`
library (X.509 structures, ASN.1 encoding, ECDSA/RSA, hashing) and `python-pkcs11` (the
standard interface to an HSM). Both are primitive libraries in the same sense OpenSSL is —
they provide algorithms and encodings, not certificate-authority behaviour.

No CA *product* is wrapped, embedded, forked or called. There is no EJBCA, Dogtag, step-ca,
OpenXPKI or cfssl anywhere in the dependency graph. The policy decisions that make something
a CA — hierarchy, issuance rules, the RA workflow, revocation semantics, CRL scheduling, OCSP
responder behaviour, path validation — are all implemented in this repository:

| Concern | File | Lines of policy |
|---|---|---|
| Key custody | [`pki/keystore.py`](../apps/api/app/pki/keystore.py) | software + PKCS#11 keystores behind one ABC |
| Hierarchy, certificate construction | [`pki/ca.py`](../apps/api/app/pki/ca.py) | root, issuing, OCSP responder, cross-certification |
| Registration Authority | [`pki/ra.py`](../apps/api/app/pki/ra.py) | enrolment, review, dual control, SoD |
| Certificate lifecycle | [`pki/lifecycle.py`](../apps/api/app/pki/lifecycle.py) | issue, renew, suspend, resume, revoke, expire |
| Revocation lists | [`pki/crl.py`](../apps/api/app/pki/crl.py) | full + delta CRLs |
| OCSP responder | [`pki/ocsp.py`](../apps/api/app/pki/ocsp.py) | RFC 6960 |
| Path validation | [`pki/validate.py`](../apps/api/app/pki/validate.py) | RFC 5280 for third-party certificates |

The SBOM ([§9](#9-sbom)) lists the primitive libraries explicitly. They are dependencies in
the sense that a compiler is a dependency — the engineering is ours.

---

## 2. Hierarchy

```
                     ┌─────────────────────────────┐
                     │      Root CA (OFFLINE)      │   EC P-384 · 20 years
                     │  CN=<PKI_ROOT_CN>           │   pathLen = 1
                     │  self-signed                │   key destroyed from the online
                     └──────────────┬──────────────┘   keystore after the ceremony
                                    │ signs
                     ┌──────────────▼──────────────┐
                     │     Issuing CA (ONLINE)     │   EC P-384 · 10 years
                     │  CN=<PKI_ISSUING_CN>        │   pathLen = 0  ← cannot mint sub-CAs
                     └───────┬─────────────┬───────┘
                    signs    │             │   signs
          ┌──────────────────▼──┐       ┌──▼───────────────────────┐
          │ Signatory certs     │       │ OCSP responder cert      │
          │ EC P-256            │       │ EC P-256 · 1 year        │
          │ 730 d internal      │       │ EKU id-kp-OCSPSigning    │
          │   7 d visitor       │       │ + OCSPNoCheck            │
          │ KU: digitalSignature│       └──────────────────────────┘
          │   + contentCommitment│
          └──────────────────────┘
```

**Why this shape.**

- *`pathLen = 0` on the issuing CA.* An attacker who compromises the online CA can issue
  end-entity certificates — bad, and recoverable by revoking the CA. They cannot create a new
  sub-CA and extend the hierarchy, which would be much harder to contain.
- *A delegated OCSP responder.* Signing OCSP responses with the CA key would put that key in a
  network-facing, publicly-reachable service. The responder has its own short-lived key and
  carries `OCSPNoCheck`, so relying parties do not recurse into checking the responder's own
  revocation status (RFC 6960 §4.2.2.2.1).
- *`contentCommitment` (non-repudiation) on signatory certificates.* This is the key-usage bit
  that distinguishes a certificate meant for signing an agreement from one meant for
  authenticating a session. Without it the legal weight of the signature is materially weaker.
- *EC over RSA.* P-384 for CAs and P-256 for leaves gives equivalent-or-better security at a
  fraction of the signing cost. This matters directly for the OCSP p95 < 200 ms target, where
  the response signature dominates the request.

Provisioning is one idempotent call: `POST /pki/provision`, or
`ca.provision_hierarchy(db, tenant_id)`.

---

## 3. Key custody

`KeyStore` ([`pki/keystore.py`](../apps/api/app/pki/keystore.py)) is an ABC with two
implementations and, deliberately, **no export method**. A caller cannot serialise a private
key out of the store, so code written against the software store works unchanged against the
HSM.

### 3.1 SoftKeyStore — development and CI

Keys are generated in-process and stored in the `pki_keys` table as PKCS#8 PEM, encrypted at
rest by the existing Fernet/AES-256-GCM chain (`MFA_ENCRYPTION_KEYS`). A database dump alone
yields nothing.

It is honestly labelled: **not FIPS-validated, not tamper-resistant, not for production
signing**. `/pki/health` returns a standing warning while it is in use, and the API logs a
warning at startup in a production environment.

### 3.2 Pkcs11KeyStore — production

Keys are generated **inside** the token with `CKA_SENSITIVE=true` and
`CKA_EXTRACTABLE=false`, so "the private key never leaves the HSM" is a property enforced by
the device rather than a promise made by this code. This module only ever holds a label.

Because `cryptography`'s certificate builders want a private-key object, the store returns a
thin proxy (`_Pkcs11PrivateKeyProxy`) that forwards each `sign()` into the token. That is what
lets `ca.py` have one code path for both stores.

Configuration:

```
KEYSTORE_PROVIDER=pkcs11
HSM_LIBRARY_PATH=/usr/lib/softhsm/libsofthsm2.so
HSM_TOKEN_LABEL=cm-prod        # preferred over HSM_SLOT: slot ids renumber across reboots
HSM_PIN=<from the secret store — never a file in the repository>
```

### 3.3 Device compatibility

Any PKCS#11 v2.20+ token works. Verified interface; library paths for the common estate:

| Device | FIPS 140-2 | PKCS#11 library |
|---|---|---|
| SoftHSM2 (dev/CI only) | no | `/usr/lib/softhsm/libsofthsm2.so` |
| Thales Luna Network HSM 7 | Level 3 | `/usr/safenet/lunaclient/lib/libCryptoki2_64.so` |
| Utimaco CryptoServer CP5 | Level 3 | `/opt/utimaco/lib/libcs_pkcs11_R3.so` |
| Entrust nShield Connect XC | Level 3 | `/opt/nfast/toolkits/pkcs11/libcknfast.so` |

CI runs the real `Pkcs11KeyStore` against SoftHSM2 (job `pki-hsm`), including a test that
asserts the token *refuses* to disclose the private value. See [§10](#10-known-limits) for
what that does and does not prove.

### 3.4 Key ceremony — taking the root offline

1. Provision the hierarchy on the target host (`POST /pki/provision`).
2. Under dual witness, call `POST /pki/cas/{root_id}/offline`.
3. The response returns the root private key **once**. Write it to two separate offline media
   (e.g. encrypted USB in separate safes). It is not persisted anywhere afterwards and it
   never appears in an audit entry — only the fact of the ceremony does.
4. The keystore entry is destroyed and the CA row is flagged `is_offline`.
5. Record the ceremony: date, participants, media serial numbers, safe locations.

With an HSM the key was never online, so this step only sets the flag; the equivalent control
is the HSM's own key-backup/quorum procedure.

---

## 4. Registration Authority

**No certificate is issued without an approved RA request.** `issue_from_request()` refuses
any request that is not in `approved` state; the RA workflow is the only door.

```
enrol ──▶ pending ──▶ approved ──▶ (issue) ──▶ issued
              │
              └─────▶ rejected
```

**Identity evidence** is captured at enrolment, carried into the issuance audit entry, and is
what an auditor reads to understand *why* the CA believed the subject:

| Subject | Evidence |
|---|---|
| Internal user | OIDC / SCIM / SAML claims — issuer, subject, email, verified-email flag, groups. Where a user has only a local password account, the request records an explicit caveat so the RA officer sees that the binding is weak and must be vetted out of band. |
| External signatory | The OTP-verified binding from the visitor signing surface (Phase 2): channel, masked identifier, timestamp, IP, user agent. |

Two controls, both enforced in code and covered by tests:

- **Separation of duties** — an RA officer cannot approve their own enrolment request.
  Self-issuance would defeat the purpose of having an RA at all.
- **Dual control** (`RA_DUAL_CONTROL=true`) — two *different* officers must approve. The first
  approval is recorded and the request stays `pending`; the second promotes it to `approved`.

RA officer is restricted to `owner` / `admin`. Certificate issuance is a trust-anchor-level
power, not ordinary workspace administration.

---

## 5. Certificate lifecycle

Six operations, per RFP §4a: **enrol, issue, renew, suspend, resume, revoke** (plus an expiry
sweep).

### 5.1 One certificate per signatory

The RFP states that shared or role-based certificates are not permitted. This is enforced
twice, independently:

1. `_assert_no_active_certificate()` at issuance time, with an explanatory error.
2. A **partial unique index** on `certificates` over `(tenant_id, subject_user_id)` and
   `(tenant_id, subject_party_id)`, restricted to `status = 'active'`
   (migration [`0016_pki`](../apps/api/migrations/versions/0016_pki.py)). A code path that
   forgot to call the service layer still cannot create a second active certificate.

The index DDL is dialect-specific — Oracle has no filtered indexes, so it gets a
function-based unique index that evaluates to NULL outside the filter. See
`db_dialect.partial_unique_index`.

### 5.2 Renewal

A renewal is a **new certificate with a new serial and a new key**, never a re-dated one.
Re-dating would leave two certificates sharing a serial, which breaks CRL and OCSP lookup
outright. The subject binding is preserved and `renewed_from_id` links the chain; the previous
certificate is revoked with reason `superseded`, which both publishes it on the CRL and frees
the subject's one active slot.

### 5.3 Suspension is reversible; revocation is not

Suspension uses RFC 5280 `certificateHold` — the only reversible revocation reason. Resuming
publishes the serial with `removeFromCRL` in the next **delta** CRL, which is the only place
that code is meaningful. A relying party sees the hold lift without needing to understand
anything about this product.

`revoke()` is terminal: it refuses to un-revoke, to downgrade to a hold, or to re-revoke.

Leaf validity is always clamped to the issuing CA's own expiry — a certificate outliving its
issuer is unverifiable.

---

## 6. Revocation publishing

### 6.1 CRL

Full and delta CRLs, signed by the issuing CA, published at:

```
GET /pki/crl/{ca_id}.crl          application/pkix-crl     nextUpdate = CRL_VALIDITY_HOURS (24h)
GET /pki/crl/{ca_id}-delta.crl    application/pkix-crl     nextUpdate = CRL_DELTA_VALIDITY_HOURS (1h)
```

CRL numbers are monotonic per CA; `base_crl_number` records which full CRL the current deltas
apply to. Entries for certificates past their own validity are dropped, per RFC 5280 §5 —
otherwise the list grows without bound over a ten-year retention window.

A Celery beat (`pki.publish_crls`) republishes at **half** the validity window, so a single
failed republish still leaves a valid CRL in place for another cycle before relying parties
begin rejecting it. Revocation also publishes immediately.

Every issued certificate carries a **CRL Distribution Point** extension pointing here.

### 6.2 OCSP

```
POST /pki/ocsp        application/ocsp-request  →  application/ocsp-response
GET  /pki/ocsp/{base64}                            (RFC 6960 §A.1 GET form)
```

Both are unauthenticated by necessity: a relying party validating a signature is not a user of
this system. Three properties worth naming:

- **The nonce is echoed** (RFC 6960 §4.4.1). Without it, a stale `good` response can be
  replayed for a certificate that has since been revoked. This is the most commonly skipped
  requirement in the spec and it is a real attack.
- **`unknown` is not `good`.** A serial this CA never issued returns `unknown`. Conflating the
  two would let an attacker forge a certificate and have the responder vouch for it.
- **The issuer is identified from the request's own hashes**, not from a URL parameter — the
  AIA URL baked into a certificate carries no tenant. A request can therefore only ever resolve
  to the CA that actually signed the certificate.

Every issued certificate carries an **AIA** extension with the OCSP URL and the CA-issuers URL.

---

## 7. Third-party certificate validation

Overseas signatories who cannot be issued an MMBL certificate can sign with their own. That
requires validating a chain we did not build, which
[`pki/validate.py`](../apps/api/app/pki/validate.py) does per RFC 5280:

1. Chain construction from the leaf to a configured trust anchor.
2. Signature verification at every link.
3. Validity windows across the whole path, not just the leaf.
4. `BasicConstraints` — every intermediate must be a CA; `pathLen` enforced.
5. Key usage — intermediates need `keyCertSign`; the leaf needs `digitalSignature` or
   `contentCommitment` (and a warning is raised if it lacks non-repudiation).
6. Revocation — OCSP first (fresher and cheaper than a large CRL), CRL as fallback, governed by
   `PKI_REVOCATION_CHECK` (`off` / `soft_fail` / `hard_fail`). Responses are cached respecting
   `nextUpdate`.

`cryptography`'s own `x509.verification` was not used: it implements TLS server-authentication
semantics and performs no revocation checking, which is the wrong shape for document signing.

**Trust anchors live in the `trust_anchors` table, not a file on disk.** The store is seeded
with the roots the RFP names (DigiCert, GlobalSign, Sectigo, Entrust) and is extensible at
runtime through `POST /pki/trust-anchors`. Both additions and removals are audited.

Revocation URLs come from an untrusted certificate, so the fetcher accepts `http`/`https`
only — following arbitrary URL schemes there would be an SSRF primitive.

---

## 8. ECAC chaining readiness

MMBL asks that the issuing CA can later be re-chained to a root accredited under the
**Electronic Transactions Ordinance 2002** *without re-architecture and without reissuing
existing certificates*.

Three design choices make that true, and all three are load-bearing:

1. **The issuing CA's key and subject DN are stable.** A certificate is verified against the
   issuer's *key*. Anything that key has signed stays verifiable under any new chain.
2. **`cross_certify()` issues a second CA certificate for the same key and DN**, signed by a
   different parent. Both CA certificates coexist as rows in `certificate_authorities`;
   relying parties can build a path through either. Nothing already issued changes.
3. **Trust anchors are a table**, so adding the ECAC root is a runtime configuration change
   rather than a redeploy.

The migration path, when accreditation is granted:

```
1. Generate a CSR for the existing issuing CA key (subject DN unchanged).
2. ECAC issues a CA certificate for that key.
3. ca.cross_certify(db, issuing, parent_pem=<ecac cert>, ...)  → a second CA row.
4. validate.add_trust_anchor(db, tenant, <ecac root pem>)      → trust the new root.
5. Serve the new chain from /pki/ca/{id}.cer. Existing signatures keep validating,
   under either chain, with zero reissuance.
```

This is proven by a test, not merely asserted:
`test_pki.py::TestEcacReadiness::test_cross_certification_preserves_existing_certificates`
issues a certificate, cross-certifies the CA under a new root, and shows the **untouched**
original certificate validating under the new chain.

---

## 9. SBOM

CI job `sbom` publishes CycloneDX Bills of Materials as build artefacts on every run:

- `sbom-api.json` — `cyclonedx-bom` over `apps/api/requirements.txt`
- `sbom-web.json` — `@cyclonedx/cyclonedx-npm` over `apps/web`

Retained 90 days, so the submission can attach the exact SBOM for the commit that was
demonstrated. The cryptographic primitives (`cryptography`, `python-pkcs11`) appear there
explicitly, consistent with the sworn undertaking in [§1](#1-design-constraint-primitives-not-a-wrapped-ca).

---

## 10. Known limits

Stated plainly, because an evaluation committee will find them anyway and a bidder who names
them first is the one worth trusting.

1. **SoftHSM2 proves the code path, not the hardware.** CI shows that keys are generated
   inside a PKCS#11 token, that signing happens in the token, and that the token refuses to
   export the private value. It does not and cannot demonstrate tamper resistance or FIPS
   140-2 Level 3 validation — those are properties of the device. Production must run against
   one of the devices in [§3.3](#33-device-compatibility) and the deployment must evidence it.
2. **The software keystore is the default.** `KEYSTORE_PROVIDER=soft` unless configured
   otherwise. The MMBL deployment profile must set `pkcs11`. `/pki/health` warns until it does.
3. **Path validation does not implement name constraints or certificate policies.** The
   RFC 5280 checks implemented are listed in [§7](#7-third-party-certificate-validation);
   `NameConstraints`, `CertificatePolicies` and policy mapping are not among them. For
   document-signing certificates from the major commercial roots this is not a practical gap,
   but it is a gap, and it is on the roadmap.
4. ~~**The CA is not yet integrated into the signing path.**~~ **Closed in Phase 2.**
   `SIGNING_PROVIDER=pki` signs the executed PDF once per signatory with that signatory's own
   certificate and key (`app/pki/signer.py`), including PAdES-LTV with the embedded chain,
   locally-generated OCSP/CRL revocation data, and an RFC 3161 timestamp when `SIGNING_TSA_URL`
   is set. `SIGNING_PROVIDER=pades` (one shared organisational PKCS#12) is retained only for
   deployments with no internal CA and is **not** the RFP-compliant setting.

   PDF byte-range embedding uses **pyHanko**, which never receives a private key — see §1.
5. **OCSP p95 < 200 ms is designed for, not yet measured.** The lookup is a single indexed
   query and the responder key is EC to keep the signature cheap, but the load test that
   evidences the number is Phase 10.
6. **Oracle DDL for the partial unique index is unexercised**, like the rest of the Oracle
   support — see [`docs/25-database-portability.md`](25-database-portability.md) §5.1.

---

## 11. Test coverage

`apps/api/tests/test_pki.py` — 52 tests, all passing:

| Area | What is proven |
|---|---|
| Hierarchy | root self-signed; issuing chains to root; `pathLen=0`; delegated OCSP responder with correct EKU and `OCSPNoCheck`; provisioning idempotent; serials unpredictable |
| Keystore | no export method exists; material encrypted at rest (asserted against raw SQL, not through the decrypting column type); sign/verify round-trip; destroy |
| RA | issuance impossible without approval; rejected requests cannot issue; officer cannot approve their own request; non-admin cannot review; duplicate open requests refused; dual control needs two distinct officers; evidence reaches the audit entry |
| Issuance | chains to the issuing CA; bound to the signatory; carries `contentCommitment` and not `keyCertSign`; CDP + AIA present; shared certificate rejected; leaf never outlives the issuer |
| Lifecycle | renewal changes serial **and** key while preserving binding; suspension blocks signing; resumption restores it; revocation terminal; unknown reason rejected; expired cannot sign; expiry sweep frees the slot |
| CRL | revoked serial present and signed; active serial absent; CRL number monotonic; hold published as `certificateHold`; delta requires a base; delta marked with `DeltaCRLIndicator` |
| OCSP | good / revoked / hold with correct reasons; nonce echoed; signed by the delegated responder; unissued serial is `unknown`; malformed request does not raise; issuer resolved without a tenant hint; foreign issuer gets `unauthorized` |
| Validation | rejects with no anchors; accepts a valid third-party chain; rejects expired; rejects untrusted root; validates our own chain; anchors de-duplicate |
| ECAC | cross-certification preserves existing certificates |
| Isolation | certificates do not leak across tenants |

`apps/api/tests/test_pki_hsm.py` — 7 tests against SoftHSM2 in CI (skipped locally unless
`HSM_LIBRARY_PATH` is set).
