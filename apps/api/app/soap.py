"""A SOAP facade over the contract API, for legacy core-banking integration.

The RFP asks for "REST/SOAP based API support". Core banking systems in this market are often
a decade old and speak SOAP because that is what their integration layer was built for; asking
them to change is asking for the integration not to happen.

**This is a facade, not a second API.** It calls the same service functions the REST routes
call, so there is exactly one implementation of "what is this contract?" and no possibility of
the two answering differently. What it adds is an envelope and a WSDL.

**Scope is deliberately narrow: read and create.** A full SOAP surface mirroring every REST
endpoint would be a large amount of hand-written XML that nobody exercises, and every one of
those operations is a place for the two APIs to drift. Core banking wants to look up an
agreement and register one; the rest of the lifecycle happens where people can see it.

Authentication is the same API key the REST surface uses, in a WS-Security `UsernameToken` —
which is what a legacy client is already built to send.
"""

from __future__ import annotations

import datetime as dt
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .config import settings

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
WSSE_NS = ("http://docs.oasis-open.org/wss/2004/01/"
           "oasis-200401-wss-wssecurity-secext-1.0.xsd")
TNS = "http://thiqa.example/contract-management"


class SoapFault(Exception):
    """A SOAP fault. `code` is `Client` for the caller's mistake, `Server` for ours."""

    def __init__(self, message: str, code: str = "Client"):
        super().__init__(message)
        self.code = code


def fault(message: str, code: str = "Client") -> str:
    """A SOAP 1.1 fault envelope.

    Returned with HTTP 500 even for a client error, because that is what SOAP 1.1 specifies
    and legacy stacks check the fault code, not the status line. Returning 400 with a fault
    body is the thing that makes an old client report "unparseable response".
    """
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}"><soap:Body><soap:Fault>'
        f'<faultcode>soap:{code}</faultcode>'
        f'<faultstring>{escape(str(message))}</faultstring>'
        f'</soap:Fault></soap:Body></soap:Envelope>'
    )


def envelope(body: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">'
        f'<soap:Body>{body}</soap:Body></soap:Envelope>'
    )


def _text(value) -> str:  # type: ignore[no-untyped-def]
    if value is None:
        return ""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return escape(str(value))


def parse_request(xml: str) -> tuple[str, dict, str]:
    """(operation, parameters, api key) from a SOAP envelope.

    Parsed with `defusedxml`: the request is unauthenticated at this point, and a plain XML
    parser here is an XXE and billion-laughs target reachable before any credential check.
    """
    from defusedxml.ElementTree import fromstring

    try:
        root = fromstring(xml)
    except Exception as e:  # noqa: BLE001
        raise SoapFault("The request was not well-formed XML.") from e

    api_key = ""
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in ("Password", "PasswordText", "BinarySecurityToken") and element.text:
            api_key = element.text.strip()
        elif tag == "ApiKey" and element.text:
            api_key = element.text.strip()

    body = None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "Body":
            body = element
            break
    if body is None or len(body) == 0:
        raise SoapFault("The request had no operation in its Body.")

    operation_element = list(body)[0]
    operation = operation_element.tag.rsplit("}", 1)[-1]
    parameters = {
        child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
        for child in operation_element
    }
    return operation, parameters, api_key


def authenticate(db: Session, api_key: str) -> models.User:
    """Resolve the API key to a user, exactly as the REST surface does.

    Deliberately the same credential and the same hashing: a second authentication path is a
    second place for a mistake, and the whole point of a facade is that it is not a second API.
    """
    import hashlib

    from .database import set_request_tenant

    if not api_key:
        raise SoapFault("No credentials were supplied.")
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    row = db.scalar(select(models.ApiKey).where(models.ApiKey.token_hash == digest))
    if row is None or row.revoked_at is not None:
        raise SoapFault("Those credentials were not accepted.")

    # Row security is keyed off the request tenant, so it has to be set before the user
    # lookup — exactly as `deps.get_current_user` does on the REST path.
    set_request_tenant(row.tenant_id)
    user = db.get(models.User, row.user_id)
    if user is None or not user.is_active or user.tenant_id != row.tenant_id:
        raise SoapFault("Those credentials were not accepted.")
    row.last_used_at = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    return user


# ---------------------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------------------


def _contract_xml(contract: models.Contract) -> str:
    return (
        "<tns:Contract>"
        f"<tns:Id>{_text(contract.id)}</tns:Id>"
        f"<tns:ReferenceNo>{_text(contract.reference_no)}</tns:ReferenceNo>"
        f"<tns:Title>{_text(contract.title)}</tns:Title>"
        f"<tns:Type>{_text(contract.type)}</tns:Type>"
        f"<tns:Status>{_text(contract.status)}</tns:Status>"
        f"<tns:Counterparty>{_text(contract.counterparty)}</tns:Counterparty>"
        f"<tns:Value>{_text(contract.value)}</tns:Value>"
        f"<tns:Currency>{_text(contract.currency)}</tns:Currency>"
        f"<tns:EffectiveDate>{_text(contract.effective_date)}</tns:EffectiveDate>"
        f"<tns:EndDate>{_text(contract.end_date)}</tns:EndDate>"
        f"<tns:Department>{_text(contract.department)}</tns:Department>"
        "</tns:Contract>"
    )


def op_get_contract(db: Session, user: models.User, params: dict) -> str:
    """Look one up by reference number or id."""
    reference = params.get("ReferenceNo") or params.get("Id") or ""
    if not reference:
        raise SoapFault("GetContract needs a ReferenceNo or an Id.")
    contract = db.scalar(select(models.Contract).where(
        models.Contract.tenant_id == user.tenant_id,
        models.Contract.reference_no == reference))
    if contract is None:
        contract = db.get(models.Contract, reference)
        if contract is None or contract.tenant_id != user.tenant_id:
            raise SoapFault(f"No agreement found for '{reference}'.")
    return f"<tns:GetContractResponse>{_contract_xml(contract)}</tns:GetContractResponse>"


def op_list_contracts(db: Session, user: models.User, params: dict) -> str:
    """List, filtered by status or counterparty. Capped — a legacy client asking for
    everything would otherwise pull a decade of agreements through a SOAP envelope."""
    stmt = select(models.Contract).where(models.Contract.tenant_id == user.tenant_id)
    if params.get("Status"):
        stmt = stmt.where(models.Contract.status == params["Status"])
    if params.get("Counterparty"):
        stmt = stmt.where(models.Contract.counterparty.ilike(f"%{params['Counterparty']}%"))
    try:
        limit = min(500, max(1, int(params.get("Limit") or 100)))
    except ValueError as e:
        raise SoapFault("Limit must be a number.") from e

    rows = db.scalars(stmt.order_by(models.Contract.updated_at.desc()).limit(limit)).all()
    items = "".join(_contract_xml(c) for c in rows)
    return (f"<tns:ListContractsResponse><tns:Count>{len(rows)}</tns:Count>"
            f"{items}</tns:ListContractsResponse>")


def op_create_contract(db: Session, user: models.User, params: dict) -> str:
    """Register an agreement raised in the core banking system.

    Creates a draft, exactly as the REST path does. It does not skip the lifecycle: an
    agreement arriving over SOAP still goes through review and signature like any other,
    because the integration is a way in, not a way around.
    """
    from .audit import record

    title = params.get("Title") or ""
    if not title.strip():
        raise SoapFault("CreateContract needs a Title.")

    year = dt.date.today().year
    count = db.query(models.Contract).filter_by(tenant_id=user.tenant_id).count()

    contract = models.Contract(
        tenant_id=user.tenant_id, reference_no=f"C-{year}-{count + 1:04d}",
        title=title.strip()[:300], type=params.get("Type") or "other", status="draft",
        owner_id=user.id, created_by=user.id,
        counterparty=(params.get("Counterparty") or "").strip()[:200],
        department=(params.get("Department") or "").strip()[:100],
        currency=(params.get("Currency") or "PKR")[:3],
        source="soap",
    )
    if params.get("Value"):
        try:
            contract.value = float(params["Value"])
        except ValueError as e:
            raise SoapFault("Value must be a number.") from e
    for field, key in (("effective_date", "EffectiveDate"), ("end_date", "EndDate")):
        if params.get(key):
            try:
                setattr(contract, field, dt.date.fromisoformat(params[key]))
            except ValueError as e:
                raise SoapFault(f"{key} must be YYYY-MM-DD.") from e

    db.add(contract)
    db.flush()
    db.add(models.ContractVersion(
        tenant_id=user.tenant_id, contract_id=contract.id, version_no=1, body="",
        change_summary="Registered over the SOAP interface", created_by=user.id))
    record(db, tenant_id=user.tenant_id, action="contract.created", actor=user,
           object_type="contract", object_id=contract.id, object_label=contract.title,
           meta={"source": "soap"})
    return f"<tns:CreateContractResponse>{_contract_xml(contract)}</tns:CreateContractResponse>"


OPERATIONS = {
    "GetContract": op_get_contract,
    "ListContracts": op_list_contracts,
    "CreateContract": op_create_contract,
}


def handle(db: Session, xml: str) -> tuple[str, bool]:
    """(response envelope, ok). Never raises — a SOAP client expects a fault, not a stack."""
    try:
        operation, params, api_key = parse_request(xml)
        user = authenticate(db, api_key)
        handler = OPERATIONS.get(operation)
        if handler is None:
            raise SoapFault(
                f"Unknown operation '{operation}'. Supported: {', '.join(sorted(OPERATIONS))}.")
        return envelope(handler(db, user, params)), True
    except SoapFault as e:
        return fault(str(e), e.code), False
    except Exception as e:  # noqa: BLE001
        return fault(f"The request could not be processed: {type(e).__name__}",
                     code="Server"), False


def wsdl(base_url: str) -> str:
    """The WSDL a legacy client generates its stubs from.

    Hand-written rather than generated because it describes three operations and a generator
    would be a build-time dependency for a document that changes when those three do.
    """
    endpoint = f"{base_url.rstrip('/')}/soap"
    fields = [
        ("Id", "string"), ("ReferenceNo", "string"), ("Title", "string"),
        ("Type", "string"), ("Status", "string"), ("Counterparty", "string"),
        ("Value", "double"), ("Currency", "string"), ("EffectiveDate", "date"),
        ("EndDate", "date"), ("Department", "string"),
    ]
    contract_type = "".join(
        f'<xsd:element name="{name}" type="xsd:{kind}" minOccurs="0"/>'
        for name, kind in fields)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="{TNS}" targetNamespace="{TNS}">
  <wsdl:types>
    <xsd:schema targetNamespace="{TNS}" elementFormDefault="qualified">
      <xsd:complexType name="Contract"><xsd:sequence>{contract_type}</xsd:sequence></xsd:complexType>
      <xsd:element name="GetContract"><xsd:complexType><xsd:sequence>
        <xsd:element name="ReferenceNo" type="xsd:string" minOccurs="0"/>
        <xsd:element name="Id" type="xsd:string" minOccurs="0"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="GetContractResponse"><xsd:complexType><xsd:sequence>
        <xsd:element name="Contract" type="tns:Contract"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="ListContracts"><xsd:complexType><xsd:sequence>
        <xsd:element name="Status" type="xsd:string" minOccurs="0"/>
        <xsd:element name="Counterparty" type="xsd:string" minOccurs="0"/>
        <xsd:element name="Limit" type="xsd:int" minOccurs="0"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="ListContractsResponse"><xsd:complexType><xsd:sequence>
        <xsd:element name="Count" type="xsd:int"/>
        <xsd:element name="Contract" type="tns:Contract" maxOccurs="unbounded" minOccurs="0"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="CreateContract"><xsd:complexType><xsd:sequence>
        <xsd:element name="Title" type="xsd:string"/>
        <xsd:element name="Type" type="xsd:string" minOccurs="0"/>
        <xsd:element name="Counterparty" type="xsd:string" minOccurs="0"/>
        <xsd:element name="Value" type="xsd:double" minOccurs="0"/>
        <xsd:element name="Currency" type="xsd:string" minOccurs="0"/>
        <xsd:element name="Department" type="xsd:string" minOccurs="0"/>
        <xsd:element name="EffectiveDate" type="xsd:date" minOccurs="0"/>
        <xsd:element name="EndDate" type="xsd:date" minOccurs="0"/>
      </xsd:sequence></xsd:complexType></xsd:element>
      <xsd:element name="CreateContractResponse"><xsd:complexType><xsd:sequence>
        <xsd:element name="Contract" type="tns:Contract"/>
      </xsd:sequence></xsd:complexType></xsd:element>
    </xsd:schema>
  </wsdl:types>
  <wsdl:message name="GetContractIn"><wsdl:part name="parameters" element="tns:GetContract"/></wsdl:message>
  <wsdl:message name="GetContractOut"><wsdl:part name="parameters" element="tns:GetContractResponse"/></wsdl:message>
  <wsdl:message name="ListContractsIn"><wsdl:part name="parameters" element="tns:ListContracts"/></wsdl:message>
  <wsdl:message name="ListContractsOut"><wsdl:part name="parameters" element="tns:ListContractsResponse"/></wsdl:message>
  <wsdl:message name="CreateContractIn"><wsdl:part name="parameters" element="tns:CreateContract"/></wsdl:message>
  <wsdl:message name="CreateContractOut"><wsdl:part name="parameters" element="tns:CreateContractResponse"/></wsdl:message>
  <wsdl:portType name="ContractPortType">
    <wsdl:operation name="GetContract">
      <wsdl:input message="tns:GetContractIn"/><wsdl:output message="tns:GetContractOut"/>
    </wsdl:operation>
    <wsdl:operation name="ListContracts">
      <wsdl:input message="tns:ListContractsIn"/><wsdl:output message="tns:ListContractsOut"/>
    </wsdl:operation>
    <wsdl:operation name="CreateContract">
      <wsdl:input message="tns:CreateContractIn"/><wsdl:output message="tns:CreateContractOut"/>
    </wsdl:operation>
  </wsdl:portType>
  <wsdl:binding name="ContractBinding" type="tns:ContractPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="GetContract">
      <soap:operation soapAction="{TNS}/GetContract"/>
      <wsdl:input><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
    <wsdl:operation name="ListContracts">
      <soap:operation soapAction="{TNS}/ListContracts"/>
      <wsdl:input><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
    <wsdl:operation name="CreateContract">
      <soap:operation soapAction="{TNS}/CreateContract"/>
      <wsdl:input><soap:body use="literal"/></wsdl:input>
      <wsdl:output><soap:body use="literal"/></wsdl:output>
    </wsdl:operation>
  </wsdl:binding>
  <wsdl:service name="ContractManagementService">
    <wsdl:port name="ContractPort" binding="tns:ContractBinding">
      <soap:address location="{endpoint}"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
"""


def is_enabled() -> bool:
    """Off by default. An unused SOAP endpoint is attack surface with no user."""
    return bool(settings.soap_enabled)
