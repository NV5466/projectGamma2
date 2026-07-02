# Seed Boundary: Inductive Kickback vs Contact Bounce

## Inductive kickback

One coil-current-collapse event causes the victim transient.

```math
v_{victim}(t) \approx k\frac{di_{coil}}{dt}
```

Evidence:

- one dominant source event
- small source-victim lag
- fitted unknown gain \(k\)
- stable polarity/gain across repeated shots
- optional damped ringdown

## Contact bounce / HSIB

Many mechanical/electrical edges repeatedly excite the system.

```math
y(t)=\sum_n a_n h(t-t_n)
```

Evidence:

- repeated clustered source edges
- ringdown restarts multiple times
- logic state may chatter
- source event count is high

## Boundary rule

Damped ringing is a feature, not a class.

Inductive kickback is positive only when a single source-locked coil event explains the victim transient through unknown-gain derivative/voltage coupling.
