# Load and soak testing

The harness for the RFP's performance targets, and for acceptance criteria **AC-3 to AC-5**.

| Target | Criterion | Script |
|---|---|---|
| 100 concurrent users, one hour, within response targets | AC-3 | `loadtest.py --profile concurrent` |
| A day's peak signature volume with no failed or duplicated signature | AC-4 | `loadtest.py --profile signatures` |
| OCSP p95 < 200 ms | AC-5 | `loadtest.py --profile ocsp` |
| Search p95 < 500 ms on a ten-year corpus | AC-5 | `loadtest.py --profile search` |

---

## Why this is a script and not Locust or k6

Three reasons, in order of weight.

**The signature profile is not a load test.** It is a correctness test run under load. What it
asserts is that a day's peak volume produces exactly as many signatures as requests that
succeeded — no duplicates, none lost — and then reconciles that against the audit trail.
Expressing "and afterwards, verify the audit chain" in a load-testing DSL is harder than writing
the loop.

**No new dependency for the thing that measures the system.** The harness uses only what the API
already ships with. A performance tool that cannot be run because its own install is broken is a
performance tool nobody runs.

**The numbers have to be defensible.** Percentiles are computed from every recorded sample, not
from a sliding window or a summary the tool chose. When an evaluator asks how p95 was derived,
the answer is thirty lines of readable Python rather than a tool's documentation.

If MMBL's own performance team prefers k6 or JMeter, the profiles here translate directly — the
endpoints, payloads and assertions are all in one file.

---

## Running it

```bash
# Against UAT, with a seeded corpus
export CM_BASE_URL=https://cm-uat.mmbl.internal
export CM_API_KEY=cm_...            # a key with contract.read and contract.write

python infra/loadtest/loadtest.py --profile concurrent --users 100 --duration 3600
python infra/loadtest/loadtest.py --profile signatures --count 1200
python infra/loadtest/loadtest.py --profile ocsp --requests 5000
python infra/loadtest/loadtest.py --profile search --requests 2000

# Everything, writing a report
python infra/loadtest/loadtest.py --profile all --report report.json
```

Exit code is non-zero when a target is missed, so it can gate the M5 milestone rather than
producing a number somebody has to interpret.

---

## Seeding a realistic corpus

**Measuring against a few hundred tidy rows produces a number nobody should trust.** Search
latency in particular is meaningless without volume, and OCSP latency is meaningless without a
populated CRL.

```bash
python infra/loadtest/seed_corpus.py --contracts 100000 --years 10 --signatures 50000
```

This writes directly to the database rather than going through the API, because creating 100,000
agreements one HTTP request at a time takes hours and measures the seeding, not the system.

---

## What the report contains

For each profile: request count, error count, and the full percentile spread — p50, p75, p90,
p95, p99, max — plus throughput. The spread matters more than the headline: a p95 that passes
with a p99 three times higher is a system that is about to fail under a little more load, and a
single mean would hide that entirely.

The signature profile additionally reports:

- signatures requested, succeeded, and **recorded in the database**
- duplicate detections (must be zero)
- audit chain verification across the test period

---

## Honest limits

- **This runs against UAT, not Production.** UAT is sized at roughly half of Production, so the
  concurrency figure is a floor rather than a projection.
- **It does not test the HSM under load.** Signing throughput depends on the device, and the
  software keystore used in UAT is faster than an HSM in some operations and slower in others.
  HSM performance is a vendor figure to be verified separately at M1.
- **Network latency is whatever the test runner's network is.** Run it from inside the same
  network segment as a real client, or the numbers include a hop that production users do not
  make.
