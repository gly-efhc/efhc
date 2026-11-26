# NO_WORK_PREFIXES

Purpose: prevent new work/version numbers becoming source identities. Functional
names must survive changes of release, cycle and iteration. The sole OWNER law is
[NO_WORK_PREFIXES](https://github.com/gly-efhc/efhc_archive/blob/main/01_CANON/OWNER_DECISIONS.md#no_work_prefixes).
This document describes the executable check, not a second policy authority.

The guard compares complete Git blobs for every changed tracked path, with no
extension or directory glob exclusion. New filenames, classes, attributes,
functions and variables are inspected. Existing occurrences may remain in the
same file, but cannot increase or migrate to a new file. Removal reduces the
per-file allowance on the next main baseline. Missing history/policy or malformed
working source fails closed. The guard prints identifiers and paths, not source
lines or credentials.

Frozen historical sources remain unchanged. Exact necessary external action and
protocol references, signed prefixes, and third-party dependency versions require a path, literal, kind and reason in
`work-prefix-exceptions.json`. No wildcard exemptions or blanket version skips.
External identifiers match complete tokens; signed prefixes match exact byte literals; requirements exceptions match the complete comment, not executable constraints. The Archive records the OWNER authorization and exact entries.
PRs cannot authorize their own exemptions: the checker and policy are read from
the event's trusted base. A new exception requires a separate explicit OWNER
installation. Install only the manifest, using the exact before/after SHA-256 digests committed in the trusted checker first. A different digest or any other changed file is rejected. Unit fixtures construct forbidden identities in memory.

Local check (committed candidate):

```sh
python3 site/ci/no_work_prefixes.py --base origin/main --head HEAD
python3 -I -m unittest discover -s site/ci -p 'test_no_work_prefixes.py' -v
```

The standalone workflow runs on every push, PR, merge group and manual dispatch,
without path filters or continue-on-error. Pages and parity also require it before
their existing jobs. Initial installation is pinned to the exact previous main;
later runs execute the base revision's guard. A local PASS is not branch protection.

## Main protection

`.github/rulesets/main.json` is an importable Ruleset definition, not evidence of
activation. Import it at repository Settings → Rules → Rulesets → New ruleset →
Import a ruleset. Verify Active, main, no bypass actors, PR/review required and the
exact successful Actions context `NO_WORK_PREFIXES`. Admin credentials must create
the remote ruleset and read it back before claiming direct push is blocked. The
PR requirement also affects existing automated imports/pushes; they must use a PR,
not receive a silent bypass. Existing importer architecture is unchanged.

## Existing debt

This first protection installs no automatic rename or deletion. For each later
cleanup: inventory consumers → stable existing name → update all imports,
generators, selectors and tests together → build and rendered regression → save
checkpoint. Keep frozen references and accepted UI intact. A CSS rename is not
complete until generated assets and their consumers are verified.

For verified API, stored data, and schema compatibility identities, the manifest may bind the exact reported identity to an exact path and finite occurrence limit. A different name, location, or extra occurrence remains forbidden. A contract exception is not an exception for work labels.
