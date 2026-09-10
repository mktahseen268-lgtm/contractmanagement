"""The SOAP endpoint itself.

Separate from the REST routers because it is not REST: one path, one verb, an XML body, and a
WSDL. Mixing it into a resource router would put a document-style RPC endpoint among resources
and make both harder to read.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .. import soap
from ..database import get_db

router = APIRouter(tags=["soap"])


@router.get("/soap")
def get_wsdl(request: Request) -> Response:
    """Serve the WSDL. Legacy clients fetch this to generate their stubs."""
    if not soap.is_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="The SOAP interface is not enabled.")
    base = str(request.base_url).rstrip("/")
    return Response(content=soap.wsdl(base), media_type="text/xml")


@router.post("/soap")
async def soap_endpoint(request: Request, db: Session = Depends(get_db)) -> Response:
    """Handle one SOAP call.

    A fault comes back with HTTP 500 because that is what SOAP 1.1 specifies — legacy stacks
    read the fault code, and a 400 carrying a fault body is what makes an old client report
    "unparseable response" instead of the actual error.
    """
    if not soap.is_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="The SOAP interface is not enabled.")

    raw = (await request.body()).decode("utf-8", errors="replace")
    body, ok = soap.handle(db, raw)
    if ok:
        db.commit()
    else:
        db.rollback()
    return Response(content=body, media_type="text/xml",
                    status_code=200 if ok else 500)
