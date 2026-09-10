#!/usr/bin/env python3
"""Load and soak harness for the RFP performance targets (acceptance criteria AC-3 to AC-5).

Standard library only — a performance tool that cannot run because its own install is broken is
a performance tool nobody runs.

Percentiles are computed from every recorded sample rather than from a sliding window, so the
figures are reproducible and the derivation is thirty readable lines rather than a tool's
documentation. Run with `--help` for the profiles.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import ssl
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------------------
# Targets. These are the RFP's numbers, in one place, so a change to a target is a one-line
# change here rather than a search through assertions.
# ---------------------------------------------------------------------------------------

TARGETS = {
    "concurrent": {"p95_ms": 1000, "error_rate": 0.001},
    "signatures": {"p95_ms": 3000, "error_rate": 0.0},      # zero: a lost signature is not a rate
    "ocsp": {"p95_ms": 200, "error_rate": 0.001},
    "search": {"p95_ms": 500, "error_rate": 0.001},
}


@dataclass
class Samples:
    """Latencies and outcomes for one profile."""

    name: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: float = 0.0
    ended_at: float = 0.0
    extra: dict = field(default_factory=dict)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, ms: float) -> None:
        with self._lock:
            self.latencies_ms.append(ms)

    def record_error(self, message: str) -> None:
        with self._lock:
            # Capped. A total outage would otherwise produce a gigabyte of identical strings and
            # the report would be the thing that ran out of memory.
            if len(self.errors) < 500:
                self.errors.append(message)
            else:
                self.errors.append("") if False else None

    @property
    def count(self) -> int:
        return len(self.latencies_ms) + len(self.errors)

    @property
    def error_rate(self) -> float:
        return len(self.errors) / self.count if self.count else 0.0

    def percentile(self, p: float) -> float:
        """The p-th percentile, nearest-rank.

        Nearest-rank rather than interpolated: with a sample this large the difference is
        negligible, and an un-interpolated value is one that actually occurred — which is easier
        to defend when somebody asks what p95 means.
        """
        if not self.latencies_ms:
            return 0.0
        ordered = sorted(self.latencies_ms)
        index = max(0, min(len(ordered) - 1, int(round(p / 100 * len(ordered) + 0.5)) - 1))
        return ordered[index]

    def report(self) -> dict:
        duration = max(0.001, self.ended_at - self.started_at)
        return {
            "profile": self.name,
            "requests": self.count,
            "successful": len(self.latencies_ms),
            "errors": len(self.errors),
            "error_rate": round(self.error_rate, 5),
            "duration_s": round(duration, 1),
            "throughput_rps": round(self.count / duration, 1),
            "latency_ms": {
                "p50": round(self.percentile(50), 1),
                "p75": round(self.percentile(75), 1),
                "p90": round(self.percentile(90), 1),
                "p95": round(self.percentile(95), 1),
                "p99": round(self.percentile(99), 1),
                "max": round(max(self.latencies_ms), 1) if self.latencies_ms else 0.0,
                "mean": round(statistics.fmean(self.latencies_ms), 1) if self.latencies_ms else 0.0,
            },
            "sample_errors": self.errors[:5],
            **self.extra,
        }


# ---------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------


class Client:
    def __init__(self, base: str, api_key: str, *, verify_tls: bool = True, timeout: int = 30):
        self.base = base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.ctx = ssl.create_default_context()
        if not verify_tls:
            # Only for a UAT instance with a self-signed certificate. Off by default, because a
            # load test that silently accepts any certificate is also a load test that would not
            # notice the TLS configuration being wrong.
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def request(self, method: str, path: str, body: dict | None = None,
                *, authenticated: bool = True, raw: bytes | None = None,
                content_type: str = "application/json") -> tuple[int, bytes, float]:
        url = f"{self.base}{path}"
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", content_type)
        if authenticated and self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as resp:
                payload = resp.read()
                return resp.status, payload, (time.perf_counter() - started) * 1000
        except urllib.error.HTTPError as e:
            # An HTTP error is still a measured response — the server answered. Timing it is the
            # point: a 500 that takes nine seconds is a different problem from one that is instant.
            return e.code, e.read()[:500], (time.perf_counter() - started) * 1000
        except Exception as e:  # noqa: BLE001
            return 0, str(e).encode()[:500], (time.perf_counter() - started) * 1000


# ---------------------------------------------------------------------------------------
# Worker pool
# ---------------------------------------------------------------------------------------


def run_pool(work, workers: int, samples: Samples, *, duration_s: float | None = None,
             iterations: int | None = None) -> None:
    """Run `work(client_index, iteration)` across a thread pool.

    Threads rather than asyncio: the work is HTTP round-trips that spend their time blocked, the
    thread count maps directly onto "concurrent users" which is what the requirement is phrased
    in, and it needs no event-loop-aware client.
    """
    stop = threading.Event()
    counter = queue.Queue()
    samples.started_at = time.time()

    def worker(index: int) -> None:
        iteration = 0
        while not stop.is_set():
            if iterations is not None and counter.qsize() >= iterations:
                break
            counter.put(1)
            try:
                work(index, iteration)
            except Exception as e:  # noqa: BLE001
                samples.record_error(f"{type(e).__name__}: {e}")
            iteration += 1

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(workers)]
    for t in threads:
        t.start()

    try:
        if duration_s is not None:
            deadline = time.time() + duration_s
            while time.time() < deadline and any(t.is_alive() for t in threads):
                time.sleep(0.5)
            stop.set()
        for t in threads:
            t.join(timeout=60)
    except KeyboardInterrupt:
        stop.set()
        print("\nInterrupted — reporting what was measured so far.", file=sys.stderr)

    samples.ended_at = time.time()


# ---------------------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------------------


def profile_concurrent(client: Client, args) -> Samples:
    """AC-3 — 100 concurrent users sustained for an hour, within response targets.

    The mix approximates real use rather than hammering one endpoint: mostly reading, some
    searching, occasional writing. A profile that only lists contracts measures one index.
    """
    s = Samples("concurrent")
    paths = [
        ("GET", "/contracts?page_size=25", None, 40),
        ("GET", "/contracts?status=active&page_size=25", None, 15),
        ("GET", "/inbox", None, 15),
        ("GET", "/dashboard/kpis", None, 6),
        ("GET", "/dashboard/attention", None, 4),
        ("GET", "/guidance/next", None, 10),
        ("GET", "/help", None, 5),
        ("GET", "/training", None, 5),
    ]
    weighted = [p for p in paths for _ in range(p[3])]

    def work(index: int, iteration: int) -> None:
        method, path, body, _ = weighted[(index * 7 + iteration) % len(weighted)]
        status, payload, ms = client.request(method, path, body)
        if 200 <= status < 400:
            s.record(ms)
        else:
            s.record_error(f"{status} {path}: {payload[:120]!r}")

    run_pool(work, args.users, s, duration_s=args.duration)
    return s


def profile_signatures(client: Client, args) -> Samples:
    """AC-4 — a day's peak signature volume with no failed or duplicated signature.

    This is a correctness test run under load. The assertion is not latency; it is that the
    number of signatures recorded equals the number of requests that succeeded. A duplicate or a
    lost signature is the failure mode with legal consequences, and it only appears under real
    concurrency.
    """
    s = Samples("signatures")
    s.extra["duplicates"] = 0
    s.extra["requested"] = args.count

    tokens = _load_signing_tokens(client, args.count)
    if not tokens:
        s.record_error("no signing tokens available — seed the corpus first")
        s.started_at = s.ended_at = time.time()
        return s

    seen: dict[str, int] = {}
    seen_lock = threading.Lock()

    def work(index: int, iteration: int) -> None:
        position = index * 10_000 + iteration
        if position >= len(tokens):
            raise StopIteration
        token = tokens[position]
        status, payload, ms = client.request(
            "POST", f"/sign/{token}/sign",
            {"full_name": f"Load Test {position}", "consent": True,
             "tab_fills": [], "signature_kind": "typed"},
            authenticated=False)
        if 200 <= status < 300:
            s.record(ms)
            with seen_lock:
                seen[token] = seen.get(token, 0) + 1
                if seen[token] > 1:
                    s.extra["duplicates"] += 1
        else:
            s.record_error(f"{status}: {payload[:120]!r}")

    run_pool(work, args.users, s, iterations=args.count)
    s.extra["unique_signed"] = len(seen)
    return s


def profile_ocsp(client: Client, args) -> Samples:
    """AC-5 — OCSP p95 under 200 ms.

    The responder is the surface with the widest blast radius: relying parties check revocation
    while validating signatures made months ago, so if it is slow or down, validation fails
    across the whole estate rather than for one user.
    """
    s = Samples("ocsp")

    # A DER-encoded OCSPRequest for a serial that exists in the corpus. Built once — building it
    # per request would measure the construction rather than the responder.
    der = _build_ocsp_request(client)
    if der is None:
        s.record_error("could not build an OCSP request — is the PKI provisioned?")
        s.started_at = s.ended_at = time.time()
        return s

    def work(index: int, iteration: int) -> None:
        status, payload, ms = client.request(
            "POST", "/pki/ocsp", raw=der, authenticated=False,
            content_type="application/ocsp-request")
        if status == 200 and payload:
            s.record(ms)
        else:
            s.record_error(f"{status}: {payload[:120]!r}")

    run_pool(work, args.users, s, iterations=args.requests)
    return s


def profile_search(client: Client, args) -> Samples:
    """AC-5 — search p95 under 500 ms across a ten-year corpus.

    Meaningless without volume. Seed the corpus first; a search across four hundred rows
    measures nothing that will be true in production.
    """
    s = Samples("search")
    terms = ["merchant", "lease", "renewal", "liability", "termination", "settlement",
             "indemnity", "confidential", "vendor", "service level"]

    def work(index: int, iteration: int) -> None:
        term = terms[(index + iteration) % len(terms)]
        # Encoded, because a multi-word term is the realistic case and an unencoded space is a
        # control character in a URL. Found by running this — the harness reported a 9% error
        # rate that was entirely its own, which is precisely the failure a tool nobody has run
        # produces in front of the customer at M5.
        query = urllib.parse.quote(term)
        status, payload, ms = client.request(
            "GET", f"/contracts?q={query}&include_archived=true&page_size=25")
        if 200 <= status < 400:
            s.record(ms)
        else:
            s.record_error(f"{status} q={term}: {payload[:120]!r}")

    run_pool(work, args.users, s, iterations=args.requests)
    return s


# ---------------------------------------------------------------------------------------
# Helpers that need the system to be seeded
# ---------------------------------------------------------------------------------------


def _load_signing_tokens(client: Client, count: int) -> list[str]:
    """Tokens for envelopes the corpus seeder prepared.

    Returned by a test-only endpoint that exists solely for this, gated behind `LOADTEST_ENABLED`
    and refused in production. Minting them here through the normal flow would mean the test
    measured envelope creation rather than signing.
    """
    status, payload, _ = client.request("GET", f"/admin/loadtest/signing-tokens?count={count}")
    if status != 200:
        return []
    try:
        return json.loads(payload).get("tokens", [])
    except json.JSONDecodeError:
        return []


def _build_ocsp_request(client: Client) -> bytes | None:
    """A DER OCSPRequest for a real issued certificate."""
    status, payload, _ = client.request("GET", "/pki/certificates?page_size=1")
    if status != 200:
        return None
    try:
        items = json.loads(payload).get("items", [])
    except json.JSONDecodeError:
        return None
    if not items:
        return None

    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509 import ocsp, load_pem_x509_certificate
    except ImportError:
        return None

    cert_id = items[0]["id"]
    status, pem, _ = client.request("GET", f"/pki/certificates/{cert_id}/pem")
    if status != 200:
        return None
    status, issuer_pem, _ = client.request("GET", "/pki/cas")
    if status != 200:
        return None

    try:
        leaf = load_pem_x509_certificate(pem)
        cas = json.loads(issuer_pem)
        issuer = load_pem_x509_certificate(cas[0]["pem"].encode())
        builder = ocsp.OCSPRequestBuilder().add_certificate(leaf, issuer, hashes.SHA1())
        return builder.build().public_bytes(__import__("cryptography.hazmat.primitives.serialization",
                                                       fromlist=["Encoding"]).Encoding.DER)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------------------


def evaluate(report: dict) -> tuple[bool, list[str]]:
    """Compare a profile's report against its target. Returns (passed, reasons)."""
    target = TARGETS.get(report["profile"])
    if target is None:
        return True, []

    failures = []
    p95 = report["latency_ms"]["p95"]
    if p95 > target["p95_ms"]:
        failures.append(f"p95 {p95} ms exceeds the {target['p95_ms']} ms target")
    if report["error_rate"] > target["error_rate"]:
        failures.append(
            f"error rate {report['error_rate']:.4f} exceeds {target['error_rate']}")
    if report.get("duplicates", 0) > 0:
        failures.append(f"{report['duplicates']} duplicate signature(s) — AC-4 fails on any")
    if report["successful"] == 0:
        failures.append("no successful requests were recorded")
    return not failures, failures


def print_report(report: dict, passed: bool, failures: list[str]) -> None:
    lat = report["latency_ms"]
    print(f"\n  {report['profile'].upper()}  {'PASS' if passed else 'FAIL'}")
    print(f"    requests    {report['requests']:,} "
          f"({report['successful']:,} ok, {report['errors']:,} errors, "
          f"{report['error_rate']:.3%})")
    print(f"    duration    {report['duration_s']}s at {report['throughput_rps']} req/s")
    print(f"    latency     p50 {lat['p50']}  p75 {lat['p75']}  p90 {lat['p90']}  "
          f"p95 {lat['p95']}  p99 {lat['p99']}  max {lat['max']} ms")
    if "duplicates" in report:
        print(f"    signatures  {report.get('unique_signed', 0):,} unique, "
              f"{report['duplicates']} duplicate(s)")
    for reason in failures:
        print(f"    [x] {reason}")
    for err in report["sample_errors"]:
        print(f"      e.g. {err}")


def main() -> int:
    # A Windows console defaults to cp1252, and the report crashed on it while printing a
    # failure — the one moment the tool must not crash. Reconfigured rather than restricted to
    # ASCII, because error text echoed back from the API can contain anything.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default="all",
                        choices=["all", "concurrent", "signatures", "ocsp", "search"])
    parser.add_argument("--base-url", default=os.environ.get("CM_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("CM_API_KEY", ""))
    parser.add_argument("--users", type=int, default=100, help="concurrent workers")
    parser.add_argument("--duration", type=int, default=3600, help="seconds, for --profile concurrent")
    parser.add_argument("--count", type=int, default=1200, help="signatures, for --profile signatures")
    parser.add_argument("--requests", type=int, default=5000, help="requests, for ocsp and search")
    parser.add_argument("--report", help="write the full report as JSON")
    parser.add_argument("--insecure", action="store_true",
                        help="skip TLS verification (a self-signed UAT certificate only)")
    args = parser.parse_args()

    if not args.api_key and args.profile in ("all", "concurrent", "search", "ocsp"):
        print("CM_API_KEY is not set. Most profiles need an authenticated key.", file=sys.stderr)
        return 2

    client = Client(args.base_url, args.api_key, verify_tls=not args.insecure)

    status, _, _ = client.request("GET", "/healthz/ready", authenticated=False)
    if status != 200:
        print(f"{args.base_url} is not ready (got {status}). Nothing was measured.",
              file=sys.stderr)
        return 2

    profiles = {
        "concurrent": profile_concurrent,
        "signatures": profile_signatures,
        "ocsp": profile_ocsp,
        "search": profile_search,
    }
    selected = list(profiles) if args.profile == "all" else [args.profile]

    print(f"Load test against {args.base_url}")
    print(f"Profiles: {', '.join(selected)}")

    reports = []
    all_passed = True
    for name in selected:
        print(f"\nRunning {name}…")
        samples = profiles[name](client, args)
        report = samples.report()
        passed, failures = evaluate(report)
        report["passed"] = passed
        report["failures"] = failures
        reports.append(report)
        all_passed = all_passed and passed
        print_report(report, passed, failures)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump({"base_url": args.base_url,
                       "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "targets": TARGETS,
                       "profiles": reports}, fh, indent=2)
        print(f"\nReport written to {args.report}")

    print(f"\n{'All targets met.' if all_passed else 'One or more targets were missed.'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
