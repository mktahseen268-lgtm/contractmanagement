"""SAML 2.0 service provider.

These tests mint a real signing certificate, sign real assertions with it, and feed them
through the actual verification path. A SAML test that stubs out the signature proves nothing:
the signature *is* the security property.

The four attacks worth failing on, all covered below:

- an **unsigned** assertion (an assertion by nobody);
- one signed by the **wrong key** (an IdP we do not trust);
- one whose **audience is another service** protected by the same IdP;
- a **replay** of a previously-accepted assertion inside its validity window.

Signature verification itself is `signxml`'s, deliberately — XML signature wrapping is a
family of SSO-bypass bugs that hand-rolled verification walks straight into.

Requirements: SEC-04, INT-04.
"""

from __future__ import annotations

import base64
import datetime as dt
import uuid

import pytest

from app import saml
from app.saml import SamlError

pytest.importorskip("signxml", reason="SAML needs requirements-sso.txt")

from lxml import etree  # noqa: E402
from signxml import XMLSigner  # noqa: E402

ENTITY_ID = "https://cm.mmbl.test/auth/saml/metadata"
ACS = "https://cm.mmbl.test/auth/saml/acs"


def _keypair():
    """A throwaway IdP signing key and self-signed certificate."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test IdP")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1))
        .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    pem_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pem_cert = cert.public_bytes(serialization.Encoding.PEM).decode()
    return pem_key, pem_cert


@pytest.fixture(scope="module")
def idp():
    key, cert = _keypair()
    return {"key": key, "cert": cert}


@pytest.fixture(scope="module")
def other_idp():
    """A second, untrusted IdP — the "signed by the wrong key" case."""
    key, cert = _keypair()
    return {"key": key, "cert": cert}


@pytest.fixture(autouse=True)
def configured(monkeypatch, idp):
    from app.config import settings

    monkeypatch.setattr(settings, "saml_enabled", True)
    monkeypatch.setattr(settings, "saml_idp_sso_url", "https://login.example.com/saml2")
    monkeypatch.setattr(settings, "saml_idp_slo_url", "https://login.example.com/logout")
    monkeypatch.setattr(settings, "saml_idp_certificate", idp["cert"])
    monkeypatch.setattr(settings, "saml_sp_entity_id", ENTITY_ID)
    monkeypatch.setattr(settings, "saml_sp_base_url", "https://cm.mmbl.test")
    monkeypatch.setattr(settings, "saml_default_role", "author")
    monkeypatch.setattr(settings, "saml_group_role_map", {"CM-Managers": "manager"})
    # Each test gets a clean replay cache; otherwise one test's assertion id poisons the next.
    saml._seen_assertions.clear()
    yield
    saml._seen_assertions.clear()


def _assertion_xml(*, email="ayesha.khan@mmbl.test", name="Ayesha Khan",
                   audience=ENTITY_ID, recipient=ACS, in_response_to="",
                   not_before=None, not_on_or_after=None, groups=(),
                   assertion_id=None) -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    nb = (not_before or now - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    na = (not_on_or_after or now + dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    aid = assertion_id or f"_{uuid.uuid4().hex}"
    irt = f' InResponseTo="{in_response_to}"' if in_response_to else ""
    group_values = "".join(
        f'<saml:AttributeValue>{g}</saml:AttributeValue>' for g in groups)
    group_attr = (
        '<saml:Attribute Name="http://schemas.microsoft.com/ws/2008/06/identity/claims/groups">'
        f"{group_values}</saml:Attribute>" if groups else ""
    )
    return (
        f'<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{aid}" Version="2.0" IssueInstant="{nb}">'
        '<saml:Issuer>https://login.example.com/</saml:Issuer>'
        f'<saml:Subject><saml:NameID>{email}</saml:NameID>'
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        f'<saml:SubjectConfirmationData{irt} Recipient="{recipient}" NotOnOrAfter="{na}"/>'
        '</saml:SubjectConfirmation></saml:Subject>'
        f'<saml:Conditions NotBefore="{nb}" NotOnOrAfter="{na}">'
        f'<saml:AudienceRestriction><saml:Audience>{audience}</saml:Audience>'
        '</saml:AudienceRestriction></saml:Conditions>'
        f'<saml:AuthnStatement AuthnInstant="{nb}" SessionIndex="{aid}-session">'
        '<saml:AuthnContext><saml:AuthnContextClassRef>'
        'urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport'
        '</saml:AuthnContextClassRef></saml:AuthnContext></saml:AuthnStatement>'
        '<saml:AttributeStatement>'
        '<saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress">'
        f'<saml:AttributeValue>{email}</saml:AttributeValue></saml:Attribute>'
        '<saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/displayname">'
        f'<saml:AttributeValue>{name}</saml:AttributeValue></saml:Attribute>'
        f'{group_attr}'
        '</saml:AttributeStatement>'
        '</saml:Assertion>'
    )


def _signed(xml: str, signer) -> str:
    """Sign an assertion the way an IdP would, and base64 it as the POST binding expects."""
    root = etree.fromstring(xml.encode())
    signed = XMLSigner(
        method=__import__("signxml").methods.enveloped,
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#",
    ).sign(root, key=signer["key"], cert=signer["cert"])
    return base64.b64encode(etree.tostring(signed)).decode()


# ---------------------------------------------------------------------------------------
# Configuration gating
# ---------------------------------------------------------------------------------------


def test_saml_is_off_until_configured(monkeypatch):
    """A half-configured deployment must not advertise an ACS URL that cannot work."""
    from app.config import settings

    monkeypatch.setattr(settings, "saml_enabled", False)
    assert saml.is_enabled() is False


def test_enabling_without_a_certificate_is_still_off(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "saml_idp_certificate", "")
    assert saml.is_enabled() is False


def test_metadata_names_the_real_endpoints():
    """An entity ID that disagrees with what the service uses is the classic first-attempt
    failure — so it is generated, not hand-maintained."""
    xml = saml.metadata_xml()
    assert ENTITY_ID in xml
    assert ACS in xml
    assert "WantAssertionsSigned=\"true\"" in xml
    etree.fromstring(xml.encode())      # must be well-formed


def test_a_bare_base64_certificate_is_accepted(monkeypatch, idp):
    """IdP consoles hand the certificate out both ways; demanding one is a config failure
    that presents as "SSO is broken" hours later."""
    from app.config import settings

    body = "".join(
        line for line in idp["cert"].splitlines() if "CERTIFICATE" not in line
    )
    monkeypatch.setattr(settings, "saml_idp_certificate", body)
    assert "BEGIN CERTIFICATE" in saml._idp_certificate()


# ---------------------------------------------------------------------------------------
# The authentication request
# ---------------------------------------------------------------------------------------


def test_the_authn_request_is_deflated_and_encoded():
    import zlib
    from urllib.parse import parse_qs, urlparse

    url, request_id = saml.build_authn_request()
    # parse_qs already percent-decodes; unquoting again would turn a base64 "+" into a space.
    query = parse_qs(urlparse(url).query)
    raw = base64.b64decode(query["SAMLRequest"][0])
    xml = zlib.decompress(raw, -zlib.MAX_WBITS).decode()

    assert request_id.startswith("_")
    assert f'ID="{request_id}"' in xml
    assert ACS in xml
    assert ENTITY_ID in xml


def test_relay_state_is_carried_through():
    url, _ = saml.build_authn_request(relay_state="/contracts")
    assert "RelayState=" in url


# ---------------------------------------------------------------------------------------
# Verification — the security properties
# ---------------------------------------------------------------------------------------


def test_a_properly_signed_assertion_is_accepted(idp):
    identity = saml.parse_response(_signed(_assertion_xml(), idp))
    assert identity.email == "ayesha.khan@mmbl.test"
    assert identity.name == "Ayesha Khan"
    assert identity.session_index.endswith("-session")


def test_an_unsigned_assertion_is_rejected(idp):
    """An assertion by nobody."""
    raw = base64.b64encode(_assertion_xml().encode()).decode()
    with pytest.raises(SamlError, match="did not verify"):
        saml.parse_response(raw)


def test_an_assertion_signed_by_another_idp_is_rejected(other_idp):
    """The signature verifies — against a key we do not trust."""
    with pytest.raises(SamlError, match="did not verify"):
        saml.parse_response(_signed(_assertion_xml(), other_idp))


def test_a_tampered_assertion_is_rejected(idp):
    """Change one character of a signed assertion and the digest no longer matches."""
    signed = base64.b64decode(_signed(_assertion_xml(), idp)).decode()
    tampered = signed.replace("ayesha.khan@mmbl.test", "attacker@evil.test")
    with pytest.raises(SamlError, match="did not verify"):
        saml.parse_response(base64.b64encode(tampered.encode()).decode())


def test_an_assertion_for_another_service_is_rejected(idp):
    """Same IdP, different audience. Without this check, an assertion minted for any other
    application behind the same IdP would log someone in here."""
    raw = _signed(_assertion_xml(audience="https://someone-else.example/saml"), idp)
    with pytest.raises(SamlError, match="different service"):
        saml.parse_response(raw)


def test_an_expired_assertion_is_rejected(idp):
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    raw = _signed(_assertion_xml(
        not_before=now - dt.timedelta(hours=2),
        not_on_or_after=now - dt.timedelta(hours=1)), idp)
    with pytest.raises(SamlError, match="expired"):
        saml.parse_response(raw)


def test_an_assertion_from_the_future_is_rejected(idp):
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    raw = _signed(_assertion_xml(
        not_before=now + dt.timedelta(hours=1),
        not_on_or_after=now + dt.timedelta(hours=2)), idp)
    with pytest.raises(SamlError, match="not valid yet"):
        saml.parse_response(raw)


def test_small_clock_skew_is_tolerated(idp):
    """Tighter than this breaks on real infrastructure; looser widens the replay window."""
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    raw = _signed(_assertion_xml(
        not_before=now + dt.timedelta(minutes=2),
        not_on_or_after=now + dt.timedelta(minutes=30)), idp)
    assert saml.parse_response(raw).email == "ayesha.khan@mmbl.test"


def test_an_assertion_cannot_be_replayed(idp):
    """A captured response is otherwise a login, repeatedly, until it expires."""
    raw = _signed(_assertion_xml(), idp)
    assert saml.parse_response(raw).email
    with pytest.raises(SamlError, match="already been used"):
        saml.parse_response(raw)


def test_a_response_answering_a_different_request_is_rejected(idp):
    raw = _signed(_assertion_xml(in_response_to="_ourrequest"), idp)
    with pytest.raises(SamlError, match="does not answer our request"):
        saml.parse_response(raw, expected_request_id="_somethingelse")


def test_a_response_matching_our_request_is_accepted(idp):
    raw = _signed(_assertion_xml(in_response_to="_ourrequest"), idp)
    assert saml.parse_response(raw, expected_request_id="_ourrequest").email


def test_an_assertion_addressed_elsewhere_is_rejected(idp):
    raw = _signed(_assertion_xml(recipient="https://evil.test/acs"), idp)
    with pytest.raises(SamlError, match="addressed elsewhere"):
        saml.parse_response(raw)


def test_an_idp_initiated_assertion_is_accepted(idp):
    """No InResponseTo, because the user started at the IdP portal."""
    assert saml.parse_response(_signed(_assertion_xml(), idp)).email


def test_an_assertion_without_an_email_is_rejected(idp):
    xml = _assertion_xml().replace(
        '<saml:Attribute Name="http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress">'
        '<saml:AttributeValue>ayesha.khan@mmbl.test</saml:AttributeValue></saml:Attribute>', ""
    ).replace("<saml:NameID>ayesha.khan@mmbl.test</saml:NameID>",
              "<saml:NameID>not-an-email</saml:NameID>")
    with pytest.raises(SamlError, match="no email address"):
        saml.parse_response(_signed(xml, idp))


def test_rubbish_is_rejected_without_exploding():
    with pytest.raises(SamlError, match="not valid base64"):
        saml.parse_response("this is not base64 !!!")


# ---------------------------------------------------------------------------------------
# Group mapping
# ---------------------------------------------------------------------------------------


def test_a_mapped_group_selects_the_role(idp):
    identity = saml.parse_response(_signed(_assertion_xml(groups=["CM-Managers"]), idp))
    assert identity.groups == ["CM-Managers"]
    assert saml.role_for(identity) == "manager"


def test_an_unmapped_group_falls_back_to_the_default_role(idp):
    identity = saml.parse_response(_signed(_assertion_xml(groups=["Some-Other-Group"]), idp))
    assert saml.role_for(identity) == "author"


def test_no_groups_at_all_still_gets_the_default_role(idp):
    assert saml.role_for(saml.parse_response(_signed(_assertion_xml(), idp))) == "author"


# ---------------------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------------------


def test_logout_redirects_to_the_idp_when_it_has_an_slo_endpoint():
    assert saml.logout_redirect("ayesha@mmbl.test").startswith(
        "https://login.example.com/logout")


def test_logout_falls_back_locally_when_the_idp_has_no_slo(monkeypatch):
    """A logout that silently does nothing looks identical to one that worked, and the user
    walks away from a still-live IdP session."""
    from app.config import settings

    monkeypatch.setattr(settings, "saml_idp_slo_url", "")
    assert saml.logout_redirect("ayesha@mmbl.test").endswith("/login")


# ---------------------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------------------


def test_the_endpoints_are_absent_until_saml_is_configured(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "saml_enabled", False)
    assert client.get("/auth/saml/metadata").status_code == 404
    assert client.post("/auth/saml/acs", data={"SAMLResponse": "x"}).status_code == 404


def test_metadata_is_served_as_xml(client):
    response = client.get("/auth/saml/metadata")
    assert response.status_code == 200
    assert "xml" in response.headers["content-type"]
    assert ENTITY_ID in response.text


def test_login_redirects_to_the_idp(client):
    response = client.get("/auth/saml/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://login.example.com/saml2")


def test_a_rejected_assertion_does_not_explain_itself_to_the_browser(client, idp):
    """Telling an unauthenticated caller *why* their assertion failed is a probing oracle;
    the reason goes to the audit log instead."""
    response = client.post("/auth/saml/acs",
                           data={"SAMLResponse": base64.b64encode(b"<nope/>").decode()},
                           follow_redirects=False)
    assert response.status_code == 302
    assert "sso_error=saml_rejected" in response.headers["location"]
    assert "signature" not in response.headers["location"].lower()
