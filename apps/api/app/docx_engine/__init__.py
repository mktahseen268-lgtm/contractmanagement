"""Word (.docx) round-trip — export a contract, read back what the counterparty changed.

The RFP's most-cited supplemental requirement. External counterparties will not negotiate
inside a portal; they open the Word file, mark it up with track changes, and email it back.

    export.py      contract -> .docx, with clause numbering as real Word numbering
    importer.py    .docx -> body + tracked changes + comments, with authors and timestamps
    numbering.py   the multi-level numbering definition both sides depend on
    fixtures.py    builders that emit genuine `w:ins` / `w:del` / comments OOXML, so the
                   importer is tested against what Word really produces

Named `docx_engine` rather than `docx` so that `import docx` inside this package unambiguously
means the library, not us.
"""

from .export import render_bytes, render_contract, structure_fingerprint
from .importer import DocxComment, ImportResult, TrackedChange, import_docx, summarise

__all__ = [
    "DocxComment", "ImportResult", "TrackedChange", "import_docx", "render_bytes",
    "render_contract", "structure_fingerprint", "summarise",
]
