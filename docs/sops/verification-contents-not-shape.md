# SOP: Verification must assert CONTENTS, not SHAPE

> Description: A named failure class for change verification — the plan checked
> the *shape* of a thing (it exists, it is Ready, it answers 200) instead of its
> *contents*, so every green signal was true while the thing was broken. Rules,
> per-class assertions, and the three worked examples from 2026-08-18/19.
> Version: `2026.08.19`
> Last Updated: `2026-08-19`
> Owner: `operator + maintenance-window / upgrade-planner agents`

---

## 1) Description

On 2026-08-18/19 three separate changes shipped with verification that passed
while the change was broken. They are not three bugs; they are one failure
class:

> **The verification asserted the SHAPE of a thing rather than its CONTENTS.**
> Every green signal was literally true. None of them could distinguish
> *working* from *empty*.

The generalisable lesson, and the reason this SOP exists:

> **A health signal that cannot distinguish "working" from "empty" is not a
> health signal.**

This is the change-verification twin of
[`docs/sops/audit-script-correctness.md`](audit-script-correctness.md). There,
the defect is that a check which *could not measure* reports a result anyway
(the tri-state collapse). Here, the check measures fine — it measures the
**wrong noun**. Both produce the same operator experience: a board full of green
above a broken system, and, eventually, an operator who stops believing green.

The two SOPs share a corollary already recorded in the audit SOP as "compute the
metric the threshold names": a proxy is not the property. Shape checks are the
most seductive proxies we have, because they are cheap, they are what the
platform hands you for free, and they are *correct* — a Ready pod really is
ready. It just is not evidence of anything you cared about.

## 2) Overview

**The rule:**

> Name the property this change could silently break, and assert that property
> **directly**. Never a proxy for it. If the assertion would still go green with
> the thing empty, wrong, or unreachable, it is a shape check, not verification.

**The test to apply to every line of a Verification section:**

> Imagine the change succeeded structurally and failed substantively — the
> database restored with zero rows, the bundle built from the wrong entrypoint,
> the scrape blocked, the queue never consumed. **Does this line still go
> green?** If yes, it is not carrying any weight. Keep it (it is a useful
> floor), but it does not count as the plan's verification.

**Two corollaries:**

1. **Order matters for migrations.** The contents comparison runs *before* the
   repoint, while the old source is still authoritative and rollback is free.
   Verifying after the app is serving converts an abort into an incident.
2. **A ceiling without a floor is a shape check.** Any assertion of the form
   "X should go down" needs "and X must still be > 0", or the total
   disappearance of X reads as complete success.

### The instances (each one a test case for a new plan)

| # | Change | The green signals | What was actually true | Cost |
|---|---|---|---|---|
| 1 | **paperless-db migration** (2026-08-19, live incident) | pod Ready ✅, all 74 tables present ✅, HTTP 200 ✅ | the app was repointed at a brand-new database Django had populated with **all 74 tables and zero rows**. 714 documents invisible. Caught by a manual row count *after* it was already serving | ~15 min serving empty; recovered because the old volume was `Retain` |
| 2 | **Longhorn chart 1.12.0 → 1.12.1** (2026-08-19) | 93/93 volumes attached + healthy ✅ | the chart silently shipped `networkPolicies.restrictInternalTraffic: true` — rendering NetworkPolicies even with `networkPolicies.enabled: false` — which blocked Prometheus from `longhorn-manager:9500`. `LonghornManagerDown` ×3 fired **permanently and falsely** while Longhorn was genuinely fine | a standing false alarm, which masks the next real manager failure |
| 3 | **nextcloud whiteboard v1.5.9** (2026-08-18) | pod Ready ✅ | a Ready pod was accepted as proof; the real risk was a silently-different asset bundle. A sibling later verified that the fingerprinted bundles actually serve — the check that would have caught it | near miss |

Two adjacent instances of the same class, already recorded elsewhere:

- **Bundler bumps** "fail silently as a different bundle, not a failed build"
  ([`docs/sops/self-built-image-rebuild.md`](self-built-image-rebuild.md)). Exit
  code 0 is the shape; the served bytes are the contents.
- **Four Rails apps** are `Running` with logging configured and ship **zero**
  log documents to Elasticsearch. "Logging is configured" is shape; "documents
  arrive" is contents. Note what this does to a log-noise-reduction plan whose
  only assertion is *"line rate should fall from 45,600/h to ~300/h"*: an app
  that stopped shipping logs entirely reports **0/h** and scores as a
  spectacular success.

### Why shape checks cluster around migrations specifically

Instance 1 is the archetype and the most dangerous, because the tooling
*actively manufactures* the shape. Django, Rails and Alembic all run migrations
on boot against whatever database they are pointed at. Point them at an empty
one and they will build you a complete, correct, entirely empty schema, then
report healthy — the framework has done exactly its job. Every structural signal
is therefore not merely uninformative but **actively misleading**: the emptier
the target, the more cleanly the migration runs.

## 3) Blueprints

Write the assertion explicitly in the plan, in this form, so a vetting agent can
find it:

```
CONTENTS ASSERTION: <the property> — measured by <command>, compared to <baseline>.
```

### Blueprint A — data migration (the archetype)

Exact row counts, **both sides**, **full table set**, **before the repoint**.
Works on PG14 and PG17; `pg_stat_user_tables.n_live_tup` is a planner ESTIMATE
and must not be used (it reads 0 on a server that has not been ANALYZEd, which
manufactures a false mismatch on two identical databases):

```sql
select c.relname||'='||(xpath('/row/c/text()',
    query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                 false, true, '')))[1]::text::bigint
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where c.relkind = 'r' and n.nspname = 'public' order by c.relname;
```

```bash
diff /tmp/pgcompare-$OLD.txt /tmp/pgcompare-$NEW.txt && echo "IDENTICAL — safe to repoint"
# Any output: STOP. Do not repoint.
```

MariaDB/MySQL equivalent — `information_schema.tables.table_rows` is an InnoDB
**estimate** and is only good for the table LIST and collations; exact counts
need a generated `count(*)` per table:

```bash
# Prefer a shell loop over generated SQL — the nested quoting in a
# concat()-generates-SQL one-liner is where this check goes wrong in practice.
for T in $(mariadb -uroot -p"$P" -N -B -e \
      "select table_name from information_schema.tables
       where table_schema='DB' and table_type='BASE TABLE' order by table_name"); do
  printf "%s=%s\n" "$T" "$(mariadb -uroot -p"$P" -N -B DB -e "select count(*) from \`$T\`")"
done
```

### Blueprint B — anything scraped

```bash
# 1. the target is up (shape — necessary, not sufficient)
curl -s localhost:9090/api/v1/targets | python3 -c "
import sys, json
for t in json.load(sys.stdin)['data']['activeTargets']:
    if 'COMPONENT' in t['labels'].get('job',''):
        print(t['labels']['job'], t['health'], t.get('lastError',''))"

# 2. CONTENTS: a representative series is non-empty, over a window that STARTS
#    after the change
curl -s --get localhost:9090/api/v1/query --data-urlencode \
  'query=count(count by (instance) (SOME_COMPONENT_METRIC))' | python3 -m json.tool
# an empty `result` array is a FAILURE, not "no news"
```

### Blueprint C — anything log-emitting (assert the floor)

```bash
# documents ACTUALLY reach ES for this namespace+container, after the change
# Non-zero is the assertion. A ceiling alone would score total silence as success.
```
Filter `logs-generic-default` on `resource.attributes.k8s.namespace.name` and
`resource.attributes.k8s.container.name`, over a window starting after the roll.

### Blueprint D — cache / broker (round-trip, not `PING`)

```bash
redis-cli -a "$PW" set __verify_$$ ok EX 60
redis-cli -a "$PW" get __verify_$$          # must echo `ok`
redis-cli -a "$PW" dbsize                   # non-zero where the app has live state
redis-cli -a "$PW" del __verify_$$
# and the CONSUMER reconnected — e.g. `celery … inspect ping`, or a job delivered
```

## 4) Operational Instructions

When writing or vetting a Verification section:

1. **Write the property down first, in words.** "The document rows survive the
   restore." "Prometheus can still scrape the manager." "The browser gets the
   new bundle." Then find a command that fails when that sentence is false. If
   you cannot, you do not yet understand the change.
2. **Classify the change and take the row from the plans README table**
   (`runbooks/maintenance/plans/README.md` → "Verification must assert CONTENTS,
   not SHAPE"). Data migration, scraped component, frontend/bundler,
   log-emitting, cache/broker, storage, index, auth, bulk-content backfill.
3. **Put the contents assertion BEFORE the point of no return.** For a
   migration that is before the repoint; for a decommission, before the delete.
4. **Assert a floor on anything you expect to shrink.**
5. **Keep the shape checks.** They are a cheap floor and they catch real
   failures — they simply are not the plan's verification. Do not delete them;
   just do not let them be the only thing there.
6. **Say what the baseline is and where it was recorded.** "identical to the
   pre-check inventory" is only meaningful if the pre-check actually captured it
   in a file that survives the window.
7. **Distinguish the operator smoke test from the automated one, and mark which
   is load-bearing.** A restored-but-wrong metadata DB is invisible at pod level
   and obvious in the browser within five seconds.

## 5) Examples

### Example A — the good one (reference implementation)

`runbooks/maintenance/plans/superset-pg-cutover.md` §3 step 4 dumps exact
per-table counts from **both** databases, diffs them, and refuses to repoint on
any output — and it does this while Superset is scaled to 0, i.e. before the
cutover. Its §4(e) then names the human check as *"THE load-bearing check"*.
That plan would not have produced the paperless incident.

### Example B — the shape-only one, in a plan that knew better

`runbooks/maintenance/plans/longhorn-1.12.1-engine.md` §1b documented instance 2
in detail and closed with *"verification for a storage-layer change must include
'Prometheus can still scrape it' … §4 below inherits that."* §4 then did **not**
contain a scrape assertion. Writing the lesson in prose is not writing the
check; the check has to appear in the section that gets executed.

### Example C — the ceiling with no floor

`runbooks/maintenance/plans/ibgastro-php-strict.md` asserted a log line rate
falling from 45,600/h to ~200-500/h. With four known Rails apps shipping zero
log documents while `Running`, a result of 0/h would have been read as the best
possible outcome. Fixed by adding the floor.

## 6) Verification Tests

### Test 1: the assertion can fail
For each contents assertion, describe (or, where cheap, produce) the empty-but-
healthy state and confirm the assertion goes red. **An assertion that has never
been shown to fail is unverified** — same standard the audit SOP holds code to.

```bash
# e.g. for a migration: run the diff against an empty freshly-migrated schema
#      and confirm it produces output and the plan says STOP
```

### Test 2: the queue carries assertions
```bash
grep -L 'CONTENTS ASSERTION' runbooks/maintenance/plans/*.md
```
Absence of the marker is a prompt to read §4 by hand, not an automatic reject.
A §4 containing only `Ready` / `200` / `healthy` / `Running`, with no count,
diff, round-trip or served-bytes check, **is** a reject.

### Test 3: order is right
For every plan with a repoint/cutover/delete step, confirm the contents
comparison appears *earlier in the document* than that step.

## 7) Troubleshooting

| Symptom | Likely cause |
|---|---|
| App healthy, users see nothing | contents never asserted — the classic empty-restore (instance 1) |
| A permanent, false "component down" alert after a bump | a scrape/network posture change inside a patch release; no scrape assertion (instance 2) |
| "The upgrade went perfectly" and the metric went to zero | ceiling asserted without a floor (instance 3 / the Rails log apps) |
| Verification passes, browser shows a blank page | frontend class verified at HTTP-200 level, not served-bytes level |
| Counts match but the data is wrong | counts are necessary, not sufficient — add the human/semantic check (wrong-series metadata, swapped episodes, role downgraded to Gamma) |
| The plan documents the trap and still ships broken | the lesson was written in §1, not asserted in §4 (Example B) |

## 8) Diagnose Examples

```bash
# Which plans have no contents-style assertion at all?
# NOTE the `?` in the label: this is a PROMPT TO READ, not a verdict. It has a
# real false-positive rate — envoy-gateway-phase1/3/4 assert contents in prose
# ("assert the negative", "proven firing", "speaker discovery still works") and
# match no keyword. Per docs/sops/audit-script-correctness.md, a check that
# cries wolf gets ignored; treat every hit as "go and read §4".
for f in runbooks/maintenance/plans/*.md; do
  awk '/^#+ *[0-9]*[.)]? *Verification/{p=1;next} /^#+ *[0-9]+[.)] /{p=0} p' "$f" \
    | grep -qiE 'count\(|diff |dbsize|sha256sum|wc -c|query_to_xml|non-empty|round-trip|probe_success|tcpdump|renders|serves|self-test|inspect ping|unmatched=|CONTENTS ASSERTION' \
    || echo "SHAPE-ONLY?  $f"
done
```

```bash
# The empty-but-healthy rehearsal for a Postgres target, before you trust a restore
mise exec -- kubectl exec -n "$NS" "$NEWPOD" -- psql -U "$U" -d "$DB" -At -c \
  "select count(*) from pg_stat_user_tables;"     # tables — the SHAPE
mise exec -- kubectl exec -n "$NS" "$NEWPOD" -- psql -U "$U" -d "$DB" -At -c \
  "select sum(n) from (select (xpath('/row/c/text()',
      query_to_xml(format('select count(*) as c from %I.%I', n.nspname, c.relname),
                   false, true, '')))[1]::text::bigint as n
    from pg_class c join pg_namespace n on n.oid=c.relnamespace
    where c.relkind='r' and n.nspname='public') s;"   # ROWS — the CONTENTS
# Full schema + zero rows is the signature of instance 1.
```

## 9) Health Check

```bash
# plans queue: anything scheduled without a contents assertion
grep -L 'CONTENTS ASSERTION' runbooks/maintenance/plans/*.md

# the four log-silent apps this SOP keeps citing — is the set still four?
# (query logs-generic-default per namespace+container; a namespace with pods
#  Running and zero documents in 24h is the floor violation)
```

## 10) Security Check

- The three worked examples above are **resolved or false-positive** conditions
  and are safe to publish. A contents assertion that reveals *currently unfixed*
  exposure on a service we run belongs on the finding record, not in a plan or
  this SOP — see [`docs/sops/vulnerability-disclosure.md`](vulnerability-disclosure.md).
- Auth/SSO changes are the highest-consequence member of this class: an identity
  provider with empty `grant_types` is perfectly healthy and breaks every login
  (memory `project_authentik_blueprint_grant_types`). Never accept
  `/-/health/ready` 200 as verification of an identity change; assert a real
  login through each affected path.
- Do not paste scanner output into a plan or a commit message as a "contents
  assertion". Cite the finding ID; a **zero** is publishable, a non-zero is not.

## 11) Rollback Plan

This SOP changes documents and verification requirements, never cluster state.

```bash
git revert --no-edit <sha> && git push
```

If a change was already accepted on shape-only verification, do **not** revert
the plan — run the missing contents assertion against the live system now, and
treat a failure as an incident with the plan's own §5 rollback path. The
paperless recovery worked only because the old volume was on `Retain`; that
reclaim policy is what buys the time to discover a shape-only pass, and is
itself part of the mitigation (see
[`docs/sops/storage-safety.md`](storage-safety.md)).
