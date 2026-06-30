# Relay Contact Bounce Strategy

## Specific behavior being modeled

Contact bounce is not merely a collection of high-frequency spikes. It is a
state-machine event tied to one mechanical actuation:

```text
initial state
→ intended final state reached
→ one or more unintended departures
→ final state reached and held
```

This distinction prevents the worker from confusing bounce with:

- arcing or EFT spikes that never reverse the contact state,
- comparator or control chatter unrelated to a mechanical contact,
- multiple deliberate relay commands,
- a failed relay that never establishes the commanded state.

## AC carrier removal

For AC measurements, the observed sinusoid is a carrier, not the contact state.
A signed average over a cycle or half-cycle can collapse to zero and destroy the
behavior being measured.

The worker builds a normalized state coordinate:

```math
s(t)=\frac{m(t)-m_{open}}{m_{closed}-m_{open}}
```

where `m(t)` is a carrier-normalized magnitude. Stable pre-event and tail
regions establish the open and closed levels.

Near source zero crossings, electrical state observability is reduced. Those
samples are masked rather than treated as open-contact evidence. If the first
visible contact state follows an unobservable gap, the reported edge count is
explicitly marked as a lower bound rather than being presented as complete.

## Half-cycle-local derivative windows

Every AC half-cycle is divided into short subwindows. For each subwindow:

```math
D_w=\operatorname{median}\left(\left|\frac{ds}{dt}\right|\right)
```

```math
M_w=1.4826\operatorname{MAD}\left(\left|\frac{ds}{dt}\right|\right)
```

`D_w` measures concentrated edge activity. `M_w` measures irregularity inside
the same local window. Both survive alternating edge polarity.

The half-cycle supplies local carrier geometry. The subwindow supplies bounce
resolution.

## Classification geometry

```text
A: full state reversals after first intended contact
B: one intended transition, then stable
T: transient/runt activity without a full reversal
F: commanded final state not established and held
U: attribution or observability insufficient
```

Only `B` builds the clean transition reference. `T` does not contaminate it.

## Population modeling

Bounce and clean captures are aligned to the first intended contact transition,
not merely to the command. This separates variable operate delay from the
mechanical bounce trajectory itself.

The worker preserves:

- each explicit normalized state trajectory,
- the aligned bounce population median and spread,
- the aligned clean-transition median and spread,
- the pointwise bounce-minus-clean difference.

## Interpretation limits

The seed may report:

- make-bounce,
- break-bounce,
- repeated full reversals,
- runt or partial excursions,
- extended settling,
- low-observability edge timing,
- incomplete transition.

It does not uniquely infer oxidized contacts, spring fatigue, coil undervoltage,
mechanical misalignment, or another component-level root cause without evidence
from other seeds and measurements.
