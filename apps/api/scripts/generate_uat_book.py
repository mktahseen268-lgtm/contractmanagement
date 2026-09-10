#!/usr/bin/env python3
"""Generate the UAT test book from the automated suite.

RFP §4c asks for test-driven development with UAT scripts. This produces the numbered book from
the tests themselves rather than from a separate document, for one reason: **a hand-written UAT
book drifts.** Six weeks in, the tests have moved and the book has not, and the first person to
find out is a tester following a script for behaviour that no longer exists.

Here the book is derived. A test whose docstring names requirement IDs becomes a numbered script
that cites the test proving it; a requirement with no test appears in the gaps section rather
than being silently absent.

    python scripts/generate_uat_book.py --out ../../docs/42-uat-test-book.md

What this does NOT do is replace manual UAT. Roughly a third of the scripts in a real book are
judgement calls a machine cannot make — whether wording is clear to a branch customer, whether
an approval matrix matches actual delegation policy. Those are marked `Manual` and written by
hand; this generates the other two thirds and keeps them honest.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

# Requirement IDs as used across the submission: SOW-04, SEC-11, BB-01, PKI-06, TEC-09, INT-03.
#
# Non-capturing on the family, deliberately. `findall` with a capturing group returns the
# *group*, so the first version of this collected seven family names instead of ninety
# requirement IDs — and produced a book that grouped 1,289 scripts under "SOW" rather than one
# script under "SOW-04". A regex that is subtly wrong produces output that looks plausible.
REQUIREMENT = re.compile(r"\b(?:SOW|SEC|BB|PKI|TEC|INT|AC)-\d{2}\b")

#: Human titles for each family, so the book groups the way the Scope document does.
FAMILIES = {
    "SOW": "Scope of Work — RFP §4a(i)",
    "BB": "Branchless Banking Operations — RFP §4a(ii)",
    "TEC": "Technical Requirements — RFP §4b / §4c",
    "SEC": "Information Security — RFP §4d",
    "PKI": "PKI and eSignature",
    "INT": "Integrations",
    "AC": "Acceptance Criteria",
}

#: Requirements that can only be accepted by a person. Listed explicitly so the book states
#: which acceptance rests on a machine and which rests on judgement — a distinction a reader
#: cannot make from a passing test alone.
MANUAL_ONLY = {
    "BB-04": "Whether the flow is genuinely usable by somebody who is not digitally literate "
             "is a judgement a person from that population has to make.",
    "BB-07": "Urdu terminology has to be read by MMBL's legal team; a passing test proves the "
             "strings render, not that they are correct.",
    "BB-08": "Automated checks find roughly a third of accessibility problems. Reading order, "
             "alt-text accuracy and screen-reader completion need a human.",
    "SOW-13": "The approval matrix must match MMBL's actual delegation policy, which no test "
              "can know.",
    "SEC-21": "Third-party penetration testing, by a vendor MMBL appoints.",
    "TEC-11": "Patch turnaround is observed over time, not asserted in a test run.",
}


def collect(tests_dir: Path) -> tuple[dict, list]:
    """Walk the test files and pull out every test that cites a requirement."""
    by_requirement: dict[str, list] = defaultdict(list)
    skipped: list[str] = []

    for path in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as e:
            skipped.append(f"{path.name}: {e}")
            continue

        module_doc = ast.get_docstring(tree) or ""
        module_tests: dict[str, list[str]] = {}

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue

            doc = ast.get_docstring(node) or ""
            own = set(REQUIREMENT.findall(doc))
            if own:
                # The test names its own requirements — it becomes a script in its own right.
                for req in own:
                    by_requirement[req].append({
                        "kind": "test",
                        "file": path.name,
                        "test": node.name,
                        "line": node.lineno,
                        "doc": doc,
                        "title": _humanise(node.name),
                    })
            else:
                module_tests.setdefault(path.name, []).append(node.name)

        # Tests that do not name a requirement are attributed through their module, as ONE
        # script per requirement rather than one per test. Listing fifty tests under each of a
        # module's six requirements produces three hundred entries that a tester cannot use —
        # a book of 2,500 scripts is a book nobody opens.
        module_reqs = set(REQUIREMENT.findall(module_doc))
        inherited = module_tests.get(path.name, [])
        if module_reqs and inherited:
            for req in sorted(module_reqs):
                by_requirement[req].append({
                    "kind": "module",
                    "file": path.name,
                    "test": f"{len(inherited)} tests",
                    "line": 1,
                    "doc": _summary(module_doc),
                    "title": f"Run the {path.stem.removeprefix('test_').replace('_', ' ')} suite",
                    "tests": inherited,
                })

    return by_requirement, skipped


def _humanise(test_name: str) -> str:
    """`test_a_cc_cannot_sign` → `A CC cannot sign`.

    The test names in this suite are written as sentences precisely so this reads as a script
    step rather than an identifier.
    """
    words = test_name.removeprefix("test_").replace("_", " ").strip()
    if not words:
        return test_name
    text = words[0].upper() + words[1:]
    for acronym in ("cc", "pki", "ocsp", "crl", "sla", "otp", "api", "url", "pdf", "cnic",
                    "mfa", "siem", "cef", "hsm", "uat", "tde", "rbac"):
        text = re.sub(rf"\b{acronym}\b", acronym.upper(), text, flags=re.IGNORECASE)
    return text


def _summary(doc: str) -> str:
    """The first prose paragraph of a docstring — the 'why this matters' sentence.

    Paragraphs that are nothing but a list of requirement IDs are skipped. A test whose
    docstring opens with "SOW-01, SOW-04, BB-01." would otherwise have that echoed back as its
    rationale, which tells a tester nothing they did not already read in the heading.
    """
    if not doc:
        return ""
    for paragraph in doc.strip().split("\n\n"):
        joined = " ".join(line.strip() for line in paragraph.split("\n")).strip()
        if not joined:
            continue
        if REQUIREMENT.sub("", joined).strip(" .,;·-"):
            return joined
    return ""


def render(by_requirement: dict, all_requirements: list[str]) -> str:
    out: list[str] = []
    add = out.append

    covered = sorted(by_requirement)
    uncovered = [r for r in all_requirements if r not in by_requirement]
    total_scripts = sum(len(v) for v in by_requirement.values())

    add("# UAT Test Book")
    add("")
    add("**Generated from the automated suite — do not edit by hand.**")
    add("")
    add("```")
    add("python apps/api/scripts/generate_uat_book.py --out docs/42-uat-test-book.md")
    add("```")
    add("")
    add("Every script below cites the test that proves it. A hand-written UAT book drifts: six ")
    add("weeks in, the tests have moved and the book has not, and the first person to find out is ")
    add("a tester following a script for behaviour that no longer exists. Deriving it means the ")
    add("book cannot describe something that is not tested, and a requirement with no test appears ")
    add("in §3 rather than being silently absent.")
    add("")
    add("---")
    add("")
    add("## 1. Summary")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| Requirements with automated coverage | **{len(covered)}** |")
    add(f"| Generated scripts | **{total_scripts}** |")
    add(f"| Requirements needing manual acceptance | {len(MANUAL_ONLY)} |")
    add(f"| Requirements with no cited test | {len(uncovered)} |")
    add("")
    add("### How to execute a script")
    add("")
    add("Each script gives the role, the steps, and the expected result. Record **pass**, **fail** ")
    add("or **blocked** against the script number, with the tester's name and the date. A script ")
    add("marked `Automated by` also runs in CI on every change — executing it manually in UAT ")
    add("confirms the behaviour in MMBL's own environment with MMBL's own data, which is what UAT ")
    add("is actually for.")
    add("")
    add("---")
    add("")
    add("## 2. Scripts")
    add("")

    for family, family_title in FAMILIES.items():
        family_reqs = [r for r in covered if r.startswith(family + "-")]
        if not family_reqs:
            continue
        add(f"### {family_title}")
        add("")
        for req in sorted(family_reqs):
            entries = by_requirement[req]
            add(f"#### {req}")
            add("")
            if req in MANUAL_ONLY:
                add(f"> **Also requires manual acceptance.** {MANUAL_ONLY[req]}")
                add("")
            for i, entry in enumerate(entries, start=1):
                script_id = f"UAT-{req}-{i:02d}"
                add(f"**{script_id}** · {entry['title']}")
                add("")
                summary = _summary(entry["doc"])
                if summary:
                    add(f"*Why it matters:* {summary}")
                    add("")
                if entry["kind"] == "module":
                    add(f"*Automated by:* `{entry['file']}` — {entry['test']}")
                    add("")
                    add("<details><summary>Tests in this script</summary>")
                    add("")
                    for name in entry["tests"]:
                        add(f"- `{name}` — {_humanise(name)}")
                    add("")
                    add("</details>")
                else:
                    add(f"*Automated by:* `{entry['file']}::{entry['test']}` "
                        f"(line {entry['line']})")
                add("")
            add("")
        add("")

    add("---")
    add("")
    add("## 3. Requirements with no cited test")
    add("")
    if not uncovered:
        add("None — every requirement in the Compliance Matrix cites at least one test.")
    else:
        add("These are listed rather than omitted. Each is either accepted manually, scheduled to ")
        add("a milestone, or out of scope — the Compliance Matrix says which.")
        add("")
        add("| Requirement | Why there is no automated script |")
        add("|---|---|")
        for req in uncovered:
            reason = MANUAL_ONLY.get(req, "See the Compliance Matrix — scheduled, manual, or out of scope.")
            add(f"| {req} | {reason} |")
    add("")

    add("---")
    add("")
    add("## 4. Manual scripts")
    add("")
    add("Written by hand because they need judgement a test cannot make. They are listed here so ")
    add("the book is complete; the scripts themselves are maintained alongside it.")
    add("")
    add("| Requirement | Why a person has to accept it |")
    add("|---|---|")
    for req, reason in sorted(MANUAL_ONLY.items()):
        add(f"| {req} | {reason} |")
    add("")

    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tests", default=str(Path(__file__).parent.parent / "tests"))
    parser.add_argument("--out", help="write to this path instead of stdout")
    parser.add_argument("--requirements",
                        help="a file of requirement IDs, one per line, to report gaps against")
    args = parser.parse_args()

    tests_dir = Path(args.tests)
    if not tests_dir.is_dir():
        print(f"No test directory at {tests_dir}", file=sys.stderr)
        return 2

    by_requirement, skipped = collect(tests_dir)
    for problem in skipped:
        print(f"warning: could not parse {problem}", file=sys.stderr)

    all_requirements: list[str] = []
    if args.requirements:
        all_requirements = [line.strip() for line in
                            Path(args.requirements).read_text(encoding="utf-8").splitlines()
                            if REQUIREMENT.fullmatch(line.strip())]

    book = render(by_requirement, all_requirements)

    if args.out:
        Path(args.out).write_text(book, encoding="utf-8")
        scripts = sum(len(v) for v in by_requirement.values())
        print(f"Wrote {args.out}: {scripts} scripts across "
              f"{len(by_requirement)} requirements")
    else:
        sys.stdout.write(book)
    return 0


if __name__ == "__main__":
    sys.exit(main())
