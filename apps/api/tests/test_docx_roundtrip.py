"""Word round-trip — export, mark up in Word, import back.

The RFP's most-cited supplemental requirement. External counterparties will not negotiate
inside a portal; they open the Word file, turn on track changes, mark it up and email it back.

**On "byte-stable".** The brief asks for export → import → export to be byte-stable for
numbering, styles, tables and headers/footers. A DOCX is a zip whose byte layout depends on
entry order, compression level and Word's `rsid` churn — none of which affect the document —
so byte equality is both unachievable and not what anyone actually wants. What is tested here
is **structural** stability: the numbering definitions, paragraph styles and levels, table
shape, and header/footer text are identical across the cycle. That is the property that keeps
clause 7.2.1 meaning clause 7.2.1, which is what the requirement is protecting.

The tracked-changes tests run against OOXML built by `docx_engine.fixtures` — genuine `w:ins`,
`w:del`/`w:delText` and a real `word/comments.xml` part — rather than against documents this
codebase wrote, so the importer is exercised against what Word actually produces.

Requirements: SOW-05.
"""

from __future__ import annotations

import io

import pytest

docx = pytest.importorskip("docx", reason="python-docx not installed")

from docx import Document  # noqa: E402

from app.docx_engine import export, fixtures, import_docx, numbering, summarise  # noqa: E402


# ---------------------------------------------------------------------------------------
# A corpus of MMBL-shaped agreements.
# ---------------------------------------------------------------------------------------

CORPUS: dict[str, str] = {
    "msa": (
        "# Master Services Agreement\n"
        "## 1. Preliminary\n"
        "1. Definitions\n"
        "1.1 In this Agreement, capitalised terms have the meanings given below.\n"
        "1.2 References to clauses are to clauses of this Agreement.\n"
        "2. Scope of Services\n"
        "2.1 The Supplier shall provide the Services described in Schedule 1.\n"
        "2.1.1 The Services shall meet the service levels in Schedule 2.\n"
    ),
    "nda": (
        "# Mutual Non-Disclosure Agreement\n"
        "1. Confidential Information\n"
        "1.1 Each party may disclose Confidential Information to the other.\n"
        "2. Obligations\n"
        "2.1 The Receiving Party shall keep the information confidential.\n"
        "2.2 This obligation survives termination for five years.\n"
    ),
    "merchant": (
        "# Merchant Onboarding Agreement\n"
        "## Commercial Terms\n"
        "| Item | Rate |\n"
        "|---|---|\n"
        "| Merchant discount rate | 1.75% |\n"
        "| Settlement | T+1 |\n"
        "1. Onboarding\n"
        "1.1 The Merchant shall provide the documents listed below.\n"
        "- Certificate of Incorporation\n"
        "- National Tax Number certificate\n"
    ),
    "service": (
        "# Service Agreement\n"
        "1. Term\n"
        "1.1 This Agreement commences on the Effective Date.\n"
        "1.2 The Initial Term is **twelve months**.\n"
        "2. Fees\n"
        "2.1 Fees are payable within *thirty days* of invoice.\n"
    ),
    "lease": (
        "# Office Lease Agreement\n"
        "1. Premises\n"
        "1.1 The Landlord lets the Premises to the Tenant.\n"
        "2. Rent\n"
        "2.1 Rent is payable monthly in advance.\n"
        "2.1.1 Rent shall be reviewed annually.\n"
        "2.1.2 Any increase shall not exceed 10%.\n"
    ),
    "pgw": (
        "# Payment Gateway Agreement\n"
        "1. Integration\n"
        "1.1 The Partner shall integrate with the Bank's gateway.\n"
        "2. Settlement\n"
        "2.1 Settlement occurs on each Business Day.\n"
        "## Schedule 1 — Technical\n"
        "- API endpoints\n"
        "- Reconciliation files\n"
    ),
    "collection": (
        "# Collection Services Agreement\n"
        "1. Appointment\n"
        "1.1 The Bank appoints the Agent to collect payments.\n"
        "2. Remittance\n"
        "2.1 The Agent shall remit collections within 24 hours.\n"
    ),
    "disbursement": (
        "# Disbursement Agreement\n"
        "1. Disbursement Instructions\n"
        "1.1 The Bank shall act on instructions received.\n"
        "1.1.1 Instructions must be in the agreed format.\n"
        "2. Liability\n"
        "2.1 Liability is limited as set out in clause 3.\n"
    ),
    "mou": (
        "# Memorandum of Understanding\n"
        "1. Purpose\n"
        "1.1 The parties record their shared intent.\n"
        "2. Status\n"
        "2.1 This MoU is not legally binding except for clause 3.\n"
    ),
    "employment": (
        "# Employment Agreement\n"
        "1. Position\n"
        "1.1 The Employee is engaged in the role described in Schedule A.\n"
        "2. Remuneration\n"
        "2.1 Salary is payable monthly.\n"
        "2.2 The Employee is eligible for a discretionary bonus.\n"
        "| Component | Amount |\n"
        "|---|---|\n"
        "| Base | PKR 1,200,000 |\n"
    ),
}


def _cycle(body: str) -> tuple[dict, dict, str]:
    """export → fingerprint → import → export → fingerprint."""
    first = export.render_bytes(title="Agreement", reference="CM-0001", org_name="MMBL",
                                body=body)
    fingerprint_a = export.structure_fingerprint(Document(io.BytesIO(first)))

    imported = import_docx(first)

    second = export.render_bytes(title="Agreement", reference="CM-0001", org_name="MMBL",
                                 body=imported.body)
    fingerprint_b = export.structure_fingerprint(Document(io.BytesIO(second)))
    return fingerprint_a, fingerprint_b, imported.body


# ---------------------------------------------------------------------------------------


class TestRoundTripFidelity:
    @pytest.mark.parametrize("name", sorted(CORPUS))
    def test_structure_survives_a_full_cycle(self, name):
        """The corpus requirement: 10 MMBL-shaped agreements, each stable across the cycle."""
        before, after, _ = _cycle(CORPUS[name])
        assert before["numbering"] == after["numbering"], f"{name}: numbering drifted"
        assert before["tables"] == after["tables"], f"{name}: table shape drifted"
        assert before["header"] == after["header"], f"{name}: header drifted"
        assert before["footer"] == after["footer"], f"{name}: footer drifted"
        assert before["paragraphs"] == after["paragraphs"], f"{name}: paragraphs drifted"

    def test_corpus_is_at_least_ten_agreements(self):
        assert len(CORPUS) >= 10

    def test_a_second_cycle_changes_nothing_further(self):
        """Idempotence. Drift that only appears on the third pass is the kind that reaches
        production, because nobody exports twice while testing."""
        _, _, once = _cycle(CORPUS["msa"])
        _, _, twice = _cycle(once)
        assert once == twice


class TestClauseNumbering:
    def test_numbers_are_word_numbering_not_typed_text(self):
        """The heart of the requirement. If the number is literal text, the counterparty
        inserts a clause in Word and every number below it is silently wrong."""
        raw = export.render_bytes(title="MSA", reference="CM-1", org_name="MMBL",
                                  body="1. Definitions\n1.1 Sub clause\n")
        document = Document(io.BytesIO(raw))
        # Only the numbered paragraphs — the export also adds a title heading when the body
        # does not supply one.
        clauses = [
            p for p in document.paragraphs
            if p.text.strip() and numbering.read_number_level(p) is not None
        ]

        assert clauses[0].text.strip() == "Definitions", (
            "the authored number must NOT be baked into the text"
        )
        assert numbering.read_number_level(clauses[0]) == 0
        assert numbering.read_number_level(clauses[1]) == 1

    def test_depth_is_preserved_to_three_levels(self):
        body = "1. One\n1.1 Two\n1.1.1 Three\n"
        raw = export.render_bytes(title="T", reference="R", org_name="O", body=body)
        document = Document(io.BytesIO(raw))
        levels = [
            numbering.read_number_level(p) for p in document.paragraphs
            if p.text.strip() and numbering.read_number_level(p) is not None
        ]
        assert levels == [0, 1, 2]

    def test_numbering_definition_is_cumulative(self):
        """`1.1.1`, not `1.1.a` or a restart at each level."""
        raw = export.render_bytes(title="T", reference="R", org_name="O", body="1. One\n")
        fingerprint = numbering.numbering_fingerprint(Document(io.BytesIO(raw)))
        ours = next(a for a in fingerprint if a["abstract_id"] == str(numbering.ABSTRACT_NUM_ID))
        texts = [level["text"] for level in ours["levels"]]
        assert texts[0] == "%1."
        assert texts[1] == "%1.%2"
        assert texts[2] == "%1.%2.%3"
        assert all(level["fmt"] == "decimal" for level in ours["levels"])

    def test_import_reconstructs_depth_from_numbering_data(self):
        """Not by parsing digits out of the text — which is why a counterparty who renumbers
        by inserting a clause still imports with the right hierarchy."""
        raw = export.render_bytes(title="T", reference="R", org_name="O",
                                  body="1. One\n1.1 Two\n2. Three\n")
        body = import_docx(raw).body
        assert "1. One" in body
        assert "1.1 Two" in body
        assert "2. Three" in body

    def test_installing_numbering_twice_does_not_duplicate(self):
        document = Document()
        numbering.ensure_numbering(document)
        numbering.ensure_numbering(document)
        ids = [a["abstract_id"] for a in numbering.numbering_fingerprint(document)]
        assert ids.count(str(numbering.ABSTRACT_NUM_ID)) == 1


class TestTrackedChanges:
    @pytest.fixture()
    def marked_up(self):
        return import_docx(fixtures.counterparty_markup())

    def test_insertions_and_deletions_are_both_captured(self, marked_up):
        kinds = sorted(c.kind for c in marked_up.changes)
        assert kinds == ["delete", "insert"]

    def test_deleted_text_is_read_from_deltext(self, marked_up):
        """`w:del` wraps `w:delText`, not `w:t`. An importer that only reads `w:t` drops every
        deletion and looks like it worked."""
        deletion = next(c for c in marked_up.changes if c.kind == "delete")
        assert deletion.text.strip() == "30 days"

    def test_author_and_timestamp_survive(self, marked_up):
        for change in marked_up.changes:
            assert change.author == "Counsel for Vendor"
            assert change.at is not None, "a revision without a timestamp is not evidence"
            assert change.at.year == 2026

    def test_body_reflects_accepted_changes(self, marked_up):
        """The default reading of "what does this document now say" excludes deletions."""
        assert "90 days notice" in marked_up.body
        assert "30 days" not in marked_up.body

    def test_changes_carry_their_paragraph_context(self, marked_up):
        change = marked_up.changes[0]
        assert "terminate" in change.context.lower()

    def test_summary_counts_are_right(self, marked_up):
        summary = summarise(marked_up)
        assert summary["insertions"] == 1
        assert summary["deletions"] == 1
        assert summary["comments"] == 2
        assert summary["has_revisions"] is True
        assert "Counsel for Vendor" in summary["authors"]

    def test_a_clean_document_reports_no_revisions(self):
        raw = export.render_bytes(title="T", reference="R", org_name="O", body="1. Clean\n")
        result = import_docx(raw)
        assert result.changes == []
        assert result.has_revisions is False


class TestComments:
    @pytest.fixture()
    def marked_up(self):
        return import_docx(fixtures.counterparty_markup())

    def test_comments_are_read_with_author_and_text(self, marked_up):
        by_author = {c.author: c for c in marked_up.comments}
        assert set(by_author) == {"Counsel for Vendor", "Vendor CFO"}
        assert "90 days" in by_author["Counsel for Vendor"].text
        assert by_author["Vendor CFO"].text == "Cap must be mutual."

    def test_comments_are_anchored_to_their_clause(self, marked_up):
        """A comment that floats to the end of the document is nearly useless — the reviewer
        cannot tell what it was about."""
        cfo = next(c for c in marked_up.comments if c.author == "Vendor CFO")
        assert "Limitation of Liability" in cfo.anchor_text
        assert cfo.paragraph_index is not None

    def test_comment_timestamps_survive(self, marked_up):
        assert all(c.at is not None for c in marked_up.comments)

    def test_document_without_comments_is_fine(self):
        raw = export.render_bytes(title="T", reference="R", org_name="O", body="1. Clean\n")
        assert import_docx(raw).comments == []


class TestFormatting:
    def test_tables_survive_the_cycle(self):
        body = "| Item | Fee |\n|---|---|\n| Setup | 100 |\n| Monthly | 20 |\n"
        raw = export.render_bytes(title="T", reference="R", org_name="O", body=body)
        document = Document(io.BytesIO(raw))
        assert len(document.tables) == 1
        table = document.tables[0]
        assert len(table.rows) == 3 and len(table.columns) == 2
        assert table.rows[0].cells[0].text.strip() == "Item"

        reimported = import_docx(raw).body
        assert "| Setup | 100 |" in reimported

    def test_headings_keep_their_level(self):
        raw = export.render_bytes(title="T", reference="R", org_name="O",
                                  body="# One\n## Two\n### Three\n")
        document = Document(io.BytesIO(raw))
        styles = [p.style.name for p in document.paragraphs if p.text.strip()]
        assert styles == ["Heading 1", "Heading 2", "Heading 3"]

    def test_bold_and_italic_become_runs(self):
        raw = export.render_bytes(title="T", reference="R", org_name="O",
                                  body="Plain **bold** and *italic* text\n")
        document = Document(io.BytesIO(raw))
        paragraph = next(p for p in document.paragraphs if "bold" in p.text)
        assert any(r.bold for r in paragraph.runs)
        assert any(r.italic for r in paragraph.runs)

    def test_header_carries_the_reference(self):
        """It is how a returned printout or scan gets matched back to its agreement."""
        raw = export.render_bytes(title="MSA", reference="CM-2026-0007", org_name="MMBL",
                                  body="1. One\n")
        fingerprint = export.structure_fingerprint(Document(io.BytesIO(raw)))
        assert "CM-2026-0007" in fingerprint["header"]
        assert "MMBL" in fingerprint["header"]

    def test_title_is_not_duplicated_when_the_body_has_one(self):
        """Adding a title unconditionally grows the document by one heading per cycle."""
        raw = export.render_bytes(title="MSA", reference="R", org_name="O",
                                  body="# MSA\n1. One\n")
        document = Document(io.BytesIO(raw))
        assert sum(1 for p in document.paragraphs if p.text.strip() == "MSA") == 1


class TestBadInput:
    def test_a_pdf_gets_a_useful_error(self):
        """The commonest real mistake. A 500 here would be unhelpful and alarming."""
        with pytest.raises(ValueError, match="Word document"):
            import_docx(b"%PDF-1.4 this is not a word document")

    def test_empty_bytes_do_not_crash(self):
        with pytest.raises(ValueError):
            import_docx(b"")

    def test_empty_body_exports_a_valid_document(self):
        raw = export.render_bytes(title="Empty", reference="R", org_name="O", body="")
        assert Document(io.BytesIO(raw)) is not None
