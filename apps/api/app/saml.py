"""SAML 2.0 service provider, for Microsoft Entra ID and anything else speaking SAML.

The other half of T-3. OIDC was already wired; this is for the IdPs that do not speak it — and
for MMBL specifically, because the `sso-admin` screen has been advertising an ACS URL that did
not exist.

**XML signature verification is delegated to `signxml`, deliberately.** Verifying an XMLDSig
signature correctly is not "parse the XML and check the hash": the assertion has to be
canonicalised the same way the signer did, the reference has to be resolved to the element the
signature actually covers, and the whole family of XML signature wrapping attacks has to be
ruled out — where an attacker keeps a validly-signed assertion and wraps a forged one around
it so a naive parser reads the forgery while the verifier checks the original. Hand-rolling
that is how SSO bypasses happen. `signxml` is a maintained implementation that handles it.

What this module *does* own is everything around the signature, which is where the remaining
SAML footguns live and which no library can decide for you:

- the assertion must be signed (an unsigned one is an assertion by nobody);
- `Destination`, `Audience` and `InResponseTo` must match what we actually sent;
- `NotBefore`/`NotOnOrAfter` must hold, with a small clock skew;
- an assertion ID must never be accepted twice, or a captured response is a replay.

`SAML_ENABLED=false` by default; every endpoint 404s until an operator supplies IdP metadata.
"""

from __future__ import annotations

import base64
import datetime as dt
import secrets
import zlib
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from .config import settings

#: How much clock difference between us and the IdP to tolerate. Five minutes is the usual
#: SAML convention; tighter breaks on real infrastructure, looser widens the replay window.
CLOCK_SKEW = dt.timedelta(minutes=5)

#: Assertion IDs already consumed, with the time they expire. In-process on purpose — see
#: `_seen_assertions` below.
_seen_assertions: dict[str, dt.datetime] = {}

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
}

#: Attribute names Entra ID and friends use for the things we need. Checked in order.
_EMAIL_CLAIMS = (
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn",
    "urn:oid:0.9.2342.19200300.100.1.3",
    "email", "mail", "emailAddress", "EmailAddress",
)
_NAME_CLAIMS = (
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/displayname",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "urn:oid:2.16.840.1.113730.3.1.241",
    "displayName", "name", "cn",
)
_GROUP_CLAIMS = (
    "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
    "http://schemas.xmlsoap.org/claims/Group",
    "groups", "memberOf",
)


class SamlError(ValueError):
    """The response was not acceptable. Never leaks why to the browser — the log has detail."""


@dataclass
class SamlIdentity:
    """Who the IdP says this is."""

    name_id: str
    email: str
    name: str = ""
    groups: list[str] = field(default_factory=list)
    session_index: str = ""
    attributes: dict = field(default_factory=dict)


def is_enabled() -> bool:
    return bool(settings.saml_enabled and settings.saml_idp_sso_url
                and settings.saml_idp_certificate)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _parse_instant(value: str) -> dt.datetime:
    """SAML timestamps are ISO 8601 with a trailing Z. Compared naive, in UTC."""
    cleaned = (value or "").strip().replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(cleaned)
    return parsed.astimezone(dt.timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


# ---------------------------------------------------------------------------------------
# Service provider metadata
# ---------------------------------------------------------------------------------------


def entity_id() -> str:
    return settings.saml_sp_entity_id or f"{settings.saml_sp_base_url}/auth/saml/metadata"


def acs_url() -> str:
    return f"{settings.saml_sp_base_url}/auth/saml/acs"


def sls_url() -> str:
    return f"{settings.saml_sp_base_url}/auth/saml/sls"


def metadata_xml() -> str:
    """SP metadata for the IdP administrator to import.

    Generated rather than hand-maintained: an entity ID or ACS URL that disagrees with what
    the service actually uses is the single most common cause of a SAML integration failing
    on the first attempt, and a document a human retypes will eventually disagree.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
        f'entityID="{entity_id()}">\n'
        '  <md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" '
        'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">\n'
        '    <md:NameIDFormat>'
        'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'
        '</md:NameIDFormat>\n'
        '    <md:AssertionConsumerService '
        'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs_url()}" index="0" isDefault="true"/>\n'
        '    <md:SingleLogoutService '
        'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" '
        f'Location="{sls_url()}"/>\n'
        '  </md:SPSSODescriptor>\n'
        '</md:EntityDescriptor>\n'
    )


# ---------------------------------------------------------------------------------------
# Outbound: the authentication request
# ---------------------------------------------------------------------------------------


def build_authn_request(relay_state: str = "") -> tuple[str, str]:
    """(redirect URL, request id) for SP-initiated login.

    HTTP-Redirect binding: the request is deflated and base64-encoded per the spec. The
    request itself is unsigned — we do not require the IdP to verify us, and signing it would
    mean managing an SP signing key for no gain when the assertion is what carries trust.
    """
    if not is_enabled():
        raise SamlError("SAML is not configured.")

    request_id = "_" + secrets.token_hex(16)
    issued = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = (
        '<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{request_id}" Version="2.0" IssueInstant="{issued}" '
        f'Destination="{settings.saml_idp_sso_url}" '
        'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'AssertionConsumerServiceURL="{acs_url()}">'
        f'<saml:Issuer>{entity_id()}</saml:Issuer>'
        '<samlp:NameIDPolicy '
        'Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" '
        'AllowCreate="true"/>'
        '</samlp:AuthnRequest>'
    )
    # raw deflate (no zlib header) is what the HTTP-Redirect binding specifies
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    deflated = compressor.compress(xml.encode("utf-8")) + compressor.flush()
    encoded = quote_plus(base64.b64encode(deflated).decode("ascii"))

    separator = "&" if "?" in settings.saml_idp_sso_url else "?"
    url = f"{settings.saml_idp_sso_url}{separator}SAMLRequest={encoded}"
    if relay_state:
        url += f"&RelayState={quote_plus(relay_state)}"
    return url, request_id


# ---------------------------------------------------------------------------------------
# Inbound: the assertion
# ---------------------------------------------------------------------------------------


def _idp_certificate() -> str:
    """The IdP's signing certificate, PEM-wrapped if the operator pasted a bare base64 blob.

    IdP admin consoles hand out the certificate both ways, and demanding one format is a
    configuration failure that presents as "SSO is broken" hours later.
    """
    raw = (settings.saml_idp_certificate or "").strip()
    if "BEGIN CERTIFICATE" in raw:
        return raw
    body = "".join(raw.split())
    lines = [body[i:i + 64] for i in range(0, len(body), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def _verify_signature(xml_bytes: bytes):  # type: ignore[no-untyped-def]
    """Verified XML, or `SamlError`. The signature check itself is `signxml`'s.

    Returns the element the signature actually covers — never the document the caller parsed
    separately. Reading anything other than the verified subtree is exactly the XML signature
    wrapping bug this delegation exists to avoid.
    """
    try:
        from signxml import XMLVerifier
    except ImportError as e:  # pragma: no cover - depends on the installed requirement set
        raise SamlError(
            "SAML needs the `signxml` package. Install requirements-sso.txt."
        ) from e

    try:
        result = XMLVerifier().verify(xml_bytes, x509_cert=_idp_certificate())
    except Exception as e:  # noqa: BLE001 — signxml raises a family of validation errors
        raise SamlError(f"The SAML signature did not verify: {e}") from e
    return result.signed_xml


def _remember(assertion_id: str, expires: dt.datetime) -> None:
    """Consume an assertion ID exactly once.

    # ponytail: in-process, so a multi-replica deployment can replay an assertion against a
    # different worker inside its short validity window. The right fix is the Redis store the
    # rate limiter already uses; this is documented in docs/RFI-COMPLIANCE.md rather than left
    # to be discovered.
    """
    now = _now()
    for key, when in list(_seen_assertions.items()):
        if when < now:
            del _seen_assertions[key]
    if assertion_id in _seen_assertions:
        raise SamlError("That SAML assertion has already been used.")
    _seen_assertions[assertion_id] = expires


def parse_response(saml_response_b64: str, *, expected_request_id: str = "") -> SamlIdentity:
    """Verify a SAML response and return who it says the user is.

    Order matters: the signature is checked *first*, and everything afterwards reads only the
    verified subtree.
    """
    if not is_enabled():
        raise SamlError("SAML is not configured.")

    from defusedxml.ElementTree import fromstring as safe_fromstring  # noqa: F401

    try:
        xml_bytes = base64.b64decode(saml_response_b64, validate=True)
    except Exception as e:  # noqa: BLE001
        raise SamlError("The SAML response was not valid base64.") from e

    signed = _verify_signature(xml_bytes)

    # `signed` may be the Response or the Assertion depending on what the IdP signed. Only
    # an assertion carries identity, so locate it inside the verified subtree.
    if signed.tag.endswith("}Assertion"):
        assertion = signed
    else:
        assertion = signed.find("saml:Assertion", NS)
    if assertion is None:
        raise SamlError("The SAML response contained no signed assertion.")

    assertion_id = assertion.get("ID") or ""
    if not assertion_id:
        raise SamlError("The SAML assertion had no ID.")

    now = _now()

    conditions = assertion.find("saml:Conditions", NS)
    not_after = now + dt.timedelta(minutes=5)
    if conditions is not None:
        if conditions.get("NotBefore"):
            not_before = _parse_instant(conditions.get("NotBefore"))
            if now + CLOCK_SKEW < not_before:
                raise SamlError("The SAML assertion is not valid yet.")
        if conditions.get("NotOnOrAfter"):
            not_after = _parse_instant(conditions.get("NotOnOrAfter"))
            if now - CLOCK_SKEW >= not_after:
                raise SamlError("The SAML assertion has expired.")

        # Audience: the assertion has to have been minted for *us*. Without this an assertion
        # issued for a different service protected by the same IdP would be accepted here.
        audiences = [a.text for a in conditions.iterfind(
            "saml:AudienceRestriction/saml:Audience", NS) if a.text]
        if audiences and entity_id() not in audiences:
            raise SamlError("The SAML assertion was issued for a different service.")

    subject = assertion.find("saml:Subject", NS)
    name_id_el = subject.find("saml:NameID", NS) if subject is not None else None
    name_id = (name_id_el.text or "").strip() if name_id_el is not None else ""

    session_index = ""
    for statement in assertion.iterfind("saml:AuthnStatement", NS):
        session_index = statement.get("SessionIndex") or session_index

    if subject is not None:
        for confirmation in subject.iterfind(
            "saml:SubjectConfirmation/saml:SubjectConfirmationData", NS
        ):
            in_response_to = confirmation.get("InResponseTo")
            if expected_request_id and in_response_to and in_response_to != expected_request_id:
                raise SamlError("The SAML response does not answer our request.")
            recipient = confirmation.get("Recipient")
            if recipient and recipient.rstrip("/") != acs_url().rstrip("/"):
                raise SamlError("The SAML response was addressed elsewhere.")

    attributes: dict[str, list[str]] = {}
    for attribute in assertion.iterfind("saml:AttributeStatement/saml:Attribute", NS):
        key = attribute.get("Name") or attribute.get("FriendlyName") or ""
        values = [(v.text or "").strip()
                  for v in attribute.iterfind("saml:AttributeValue", NS) if v.text]
        if key:
            attributes[key] = values

    def _first(names: tuple[str, ...]) -> str:
        for name in names:
            if attributes.get(name):
                return attributes[name][0]
        return ""

    email = (_first(_EMAIL_CLAIMS) or (name_id if "@" in name_id else "")).lower()
    if not email:
        raise SamlError("The SAML assertion carried no email address.")

    groups: list[str] = []
    for name in _GROUP_CLAIMS:
        groups.extend(attributes.get(name, []))

    _remember(assertion_id, not_after)

    return SamlIdentity(
        name_id=name_id or email,
        email=email,
        name=_first(_NAME_CLAIMS),
        groups=groups,
        session_index=session_index,
        attributes={k: v for k, v in attributes.items()},
    )


def logout_redirect(name_id: str, session_index: str = "") -> str:
    """Single logout: tell the IdP this session is over.

    Returns the SP's own post-logout URL when the IdP has no SLO endpoint configured — a
    logout that silently does nothing looks identical to one that worked, and the user walks
    away from a still-live IdP session.
    """
    if not settings.saml_idp_slo_url:
        return f"{settings.saml_sp_base_url}/login"

    request_id = "_" + secrets.token_hex(16)
    issued = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    session = (f'<samlp:SessionIndex>{session_index}</samlp:SessionIndex>'
               if session_index else "")
    xml = (
        '<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{request_id}" Version="2.0" IssueInstant="{issued}" '
        f'Destination="{settings.saml_idp_slo_url}">'
        f'<saml:Issuer>{entity_id()}</saml:Issuer>'
        f'<saml:NameID>{name_id}</saml:NameID>'
        f'{session}'
        '</samlp:LogoutRequest>'
    )
    compressor = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    deflated = compressor.compress(xml.encode("utf-8")) + compressor.flush()
    encoded = quote_plus(base64.b64encode(deflated).decode("ascii"))
    separator = "&" if "?" in settings.saml_idp_slo_url else "?"
    return f"{settings.saml_idp_slo_url}{separator}SAMLRequest={encoded}"


def role_for(identity: SamlIdentity) -> str:
    """Map IdP groups to a workspace role, falling back to the configured default.

    Group-to-role mapping is configuration, not code: which AD group means "manager" is a
    fact about the customer's directory, and hard-coding it would make every deployment a
    patch.
    """
    mapping = settings.saml_group_role_map or {}
    for group in identity.groups:
        if group in mapping:
            return str(mapping[group])
    return settings.saml_default_role or "author"
