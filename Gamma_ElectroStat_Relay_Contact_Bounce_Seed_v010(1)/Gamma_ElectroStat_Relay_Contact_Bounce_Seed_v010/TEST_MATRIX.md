# Relay Contact Bounce Test Matrix

## Separately reported classification cases

| Family | Repetitions | Expected class |
|---|---:|---|
| AC clean close | 12 | clean_single_transition |
| DC clean close | 12 | clean_single_transition |
| AC bounce close | 12 | bounce_present |
| DC bounce close | 12 | bounce_present |
| AC bounce open | 12 | bounce_present |
| AC transient only | 12 | non_bounce_transient |
| AC failed transition | 12 | failed_transition |
| AC multiple commands | 12 | uncertain |
| AC near-zero bounce | 12 | bounce_present |

Total randomized classification cases: **108**.

Acquisition settings rotate across 100 kS/s, 200 kS/s, and 500 kS/s, with
50 Hz and 60 Hz carriers. Independent random seeds vary noise and AC phase.

## Invariant cases

Six additional tests verify:

1. AC and DC bounce feature extraction.
2. Clean-reference exclusion rules.
3. Median absolute derivative and derivative MAD output.
4. Repeated-command rejection.
5. Zero-crossing observability reporting.
6. Clean-transition wording does not imply global health.

Total pytest count: **114**.
