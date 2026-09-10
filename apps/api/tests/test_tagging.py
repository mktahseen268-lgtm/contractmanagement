"""Smart signature tagging — find the signature blocks instead of dragging boxes.

Tested against a **real rendered PDF**, not a fixture of pre-extracted text: the whole
difficulty is getting positions out of the PDF text layer and converting the coordinate
system, and a test over synthetic anchor objects would prove none of it.

Requirements: SOW-24.
"""

from __future__ import annotations

import io

import pytest

from app import tagging

pytest.importorskip("pypdf")


def _signature_page() -> bytes:
    """A page shaped like the back of a real MMBL agreement."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica", 11)
    c.drawString(72, height - 100, "IN WITNESS WHEREOF the parties have executed this Agreement.")

    # Left column — the bank.
    c.drawString(72, height - 180, "For and on behalf of")
    c.drawString(72, height - 200, "Mobilink Microfinance Bank Limited")
    c.drawString(72, height - 260, "Authorised Signatory")
    c.drawString(72, height - 290, "Name:")
    c.drawString(72, height - 310, "Designation:")
    c.drawString(72, height - 330, "Date:")

    # Right column — the merchant.
    c.drawString(320, height - 180, "For and on behalf of")
    c.drawString(320, height - 200, "The Merchant")
    c.drawString(320, height - 260, "Authorised Signatory")
    c.drawString(320, height - 290, "Name:")
    c.drawString(320, height - 310, "Designation:")
    c.drawString(320, height - 330, "Date:")

    c.showPage()
    c.save()
    return buf.getvalue()


def _plain_page() -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "This agreement sets out the terms of service between the parties.")
    c.drawString(72, 700, "No party shall assign its rights without prior written consent.")
    c.showPage()
    c.save()
    return buf.getvalue()


class TestAnchorDetection:
    def test_finds_signature_anchors_in_a_real_pdf(self):
        anchors = tagging.extract_anchors(_signature_page())
        signature_anchors = [a for a in anchors if a.kind == "signature"]
        assert len(signature_anchors) >= 2, "expected a signature block per party"

    def test_coordinates_are_normalised_with_y_from_the_top(self):
        """The codebase convention: 0..1 fractions, y growing downward. Getting this wrong
        stamps every signature at the wrong end of the page."""
        anchors = tagging.extract_anchors(_signature_page())
        assert anchors
        for a in anchors:
            assert 0.0 <= a.x <= 1.0
            assert 0.0 <= a.y <= 1.0
        # The signature block sits below the opening line, so it must have a LARGER y.
        opening = min(anchors, key=lambda a: a.y)
        assert opening.y < 0.3, "the topmost anchor should be near the top of the page"

    def test_left_and_right_columns_are_distinguished(self):
        """A two-column signature page must not collapse into one — otherwise both parties'
        tabs land on top of each other."""
        anchors = [a for a in tagging.extract_anchors(_signature_page()) if a.kind == "signature"]
        xs = sorted(a.x for a in anchors)
        assert max(xs) - min(xs) > 0.2, "expected anchors in two distinct columns"

    def test_supporting_fields_are_classified(self):
        anchors = tagging.extract_anchors(_signature_page())
        kinds = {a.kind for a in anchors}
        assert "date" in kinds
        assert "text" in kinds  # Name: / Designation:

    def test_no_anchors_in_ordinary_prose(self):
        """The word 'assign' or a clause about consent must not be read as a signature block."""
        assert tagging.extract_anchors(_plain_page()) == []

    def test_template_anchor_is_honoured(self):
        """A non-standard layout is supported by declaring an anchor, not by editing code."""
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 500, "MMBL BRANCH STAMP HERE")
        c.showPage()
        c.save()

        assert tagging.extract_anchors(buf.getvalue()) == []
        found = tagging.extract_anchors(buf.getvalue(), extra_anchors=["BRANCH STAMP HERE"])
        assert len(found) == 1 and found[0].kind == "signature"

    def test_unreadable_input_returns_empty_not_an_exception(self):
        """Automatic tagging is a convenience; failing it must never block sending."""
        assert tagging.extract_anchors(b"this is not a pdf") == []


class TestTabProposal:
    def test_tabs_are_distributed_across_signers(self):
        proposal = tagging.propose_tabs(_signature_page(), ["recipient-a", "recipient-b"])
        assert proposal.tabs
        signature_tabs = [t for t in proposal.tabs if t["kind"] == "signature"]
        assert {t["recipient_id"] for t in signature_tabs} == {"recipient-a", "recipient-b"}

    def test_supporting_fields_follow_their_nearest_signature(self):
        """A date under the merchant's signature belongs to the merchant."""
        proposal = tagging.propose_tabs(_signature_page(), ["recipient-a", "recipient-b"])
        by_recipient: dict[str, set[str]] = {}
        for tab in proposal.tabs:
            by_recipient.setdefault(tab["recipient_id"], set()).add(tab["kind"])
        # Both signers should end up with a signature and a date, not one signer with all of it.
        for kinds in by_recipient.values():
            assert "signature" in kinds
        assert all("date" in kinds for kinds in by_recipient.values())

    def test_tabs_stay_on_the_page(self):
        proposal = tagging.propose_tabs(_signature_page(), ["r1"])
        for tab in proposal.tabs:
            assert 0.0 <= tab["x"] <= 1.0
            assert 0.0 <= tab["y"] <= 1.0
            assert tab["x"] + tab["width"] <= 1.0001, "a tab ran off the right edge"

    def test_signature_tabs_are_required(self):
        proposal = tagging.propose_tabs(_signature_page(), ["r1"])
        assert all(t["required"] for t in proposal.tabs if t["kind"] == "signature")

    def test_no_signers_is_explained_not_silently_empty(self):
        proposal = tagging.propose_tabs(_signature_page(), [])
        assert proposal.tabs == []
        assert "No signers" in proposal.note

    def test_undetectable_document_explains_itself(self):
        """An empty result the user cannot interpret is a bad answer; say what to do next."""
        proposal = tagging.propose_tabs(_plain_page(), ["r1"])
        assert proposal.tabs == []
        assert "manually" in proposal.note

    def test_confidence_prefers_explicit_phrases(self):
        anchors = tagging.extract_anchors(_signature_page())
        explicit = [a for a in anchors if "on behalf of" in a.text.lower()]
        assert explicit and all(a.confidence >= 0.85 for a in explicit)


class TestDeduplication:
    def test_runs_on_one_line_collapse_to_a_single_tab(self):
        """A visual line often arrives as several text runs; three tabs on one signature line
        would be worse than none."""
        anchors = [
            tagging.Anchor(page=1, x=0.10, y=0.500, text="Authorised", kind="signature", confidence=0.65),
            tagging.Anchor(page=1, x=0.18, y=0.501, text="Signatory", kind="signature", confidence=0.9),
            tagging.Anchor(page=1, x=0.60, y=0.500, text="Authorised Signatory", kind="signature", confidence=0.9),
        ]
        kept = tagging._dedupe(anchors)
        assert len(kept) == 2, "the two runs on the same line should collapse; the far column stays"
        assert kept[0].confidence == 0.9, "the stronger match should win"
