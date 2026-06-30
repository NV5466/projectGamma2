# Gamma / ElectroStat Phase-1 Mathematical Template

## Purpose

This phase defines the inference grammar before a SPICE engine, researched seed catalogue, or field fault claim is introduced.

The system is intentionally **not** a complete digital twin. It contains:

1. a coarse connection backbone—the known roads and intersections;
2. measurement locations on that backbone;
3. location-agnostic seed families describing possible effective electrical behavior;
4. a healthy statistical model learned from WaveCompare 2;
5. a replaceable forward-model backend;
6. a ranking rule for model family, parameters, and unknown attachment location.

The backbone may remain incomplete. Unknown components, replaced devices, undocumented loads, and changed hardware are treated as latent attachments rather than missing records that must be reconstructed first.

---

## 1. Objects

### 1.1 Known connection backbone

\[
G=(V,E)
\]

- \(V\): known junctions, connectors, branch points, major sources/loads, and measurement nodes.
- \(E\): known wire or harness connections.

The graph does not contain every internal component. It records only stable connectivity information worth trusting.

### 1.2 Measurement context

A measurement is not only a waveform. It is:

\[
X=(x,q,r,\Delta t,m)
\]

where:

- \(x\): graph location;
- \(q\): measured quantity, such as voltage or current;
- \(r\): reference node, when applicable;
- \(\Delta t\): sample interval;
- \(m\): metadata such as command, operating mode, hardware unit, and date.

### 1.3 Location-agnostic physical seeds

The seed library is:

\[
\mathcal L_{\mathrm{physics}}=\{M_1,M_2,\ldots,M_K\}
\]

Each seed contains a model family, parameter names and bounds, complexity, and provenance. It does **not** contain an allowed-location list.

A model family can be tested at any graph site connected to the measurement. Connectivity determines whether a location can influence the observation; model type is inferred rather than preassigned.

### 1.4 Healthy empirical model

For aligned healthy captures \(Y_1,\ldots,Y_M\), WaveCompare 2 supplies the nominal response and aligned population. The residual matrix is:

\[
R_i=Y_i-\mu
\]

SVD gives a learned normal-variation basis:

\[
R=U\Sigma V^\top,
\qquad
U_n=V_{[:,1:k]}
\]

The stored baseline is:

\[
B_x=\{\mu_x(t),\sigma_x(t),U_{n,x},\Lambda_{n,x}\}
\]

where \(\Lambda_{n,x}\) describes the normal distribution of coordinates inside the learned noise/variation space.

---

## 2. Hypothesis

One candidate explanation is:

\[
H=(M_k,\ell,\theta)
\]

- \(M_k\): a seed family;
- \(\ell\): a latent node or edge attachment site on the known graph;
- \(\theta\): effective model parameters.

The forward backend generates:

\[
\hat Y_H(t)=F(G,X,U(t),M_k,\ell,\theta)
\]

The backend may later be LTspice/ngspice, a reduced-order analytical solver, or another simulator. The inference template must not depend on one engine.

---

## 3. Residual decomposition

After a candidate physical model explains part of the observation:

\[
e_H(t)=Y_{\mathrm{obs}}(t)-\hat Y_H(t)
\]

Project the remainder into the learned normal residual space:

\[
a_H=U_n^\top e_H
\]

\[
\hat n_H=U_n a_H
\]

\[
e_{\perp,H}=e_H-\hat n_H
\]

This separates:

- behavior explained by the candidate physical model;
- residual structure consistent with known healthy noise/variation;
- residual structure outside both spaces.

---

## 4. Initial score

The phase-1 ranking score is:

\[
J(H)=
 w_u E_{\perp}(H)
 +w_n D_n(H)
 +w_p P(\theta)
 +w_c C(M_k)
\]

where:

- \(E_{\perp}\): pointwise-variance-weighted unknown residual energy;
- \(D_n\): Mahalanobis excursion inside the normal noise coordinates;
- \(P(\theta)\): penalty for parameter values far from seed priors or bounds;
- \(C(M_k)\): complexity penalty.

Low score means the hypothesis explains the observation using a physically plausible model plus an ordinary amount of known noise.

The score is not yet a calibrated probability. Field data will be required before language such as “87% likely” is permitted.

---

## 5. Multiple locations

For measurements \(X_1,\ldots,X_m\), the same hypothesis is simulated at every location. Initial fusion is additive:

\[
J_{\mathrm{joint}}(H)=\sum_{j=1}^{m}J_j(H)
\]

This will later be replaced by a calibrated joint likelihood that accounts for cross-location covariance.

A hypothesis that can imitate one node but fails at neighboring nodes should fall in rank.

---

## 6. Active next-measurement selection

When several hypotheses remain, candidate probe points can be ranked by predicted disagreement:

\[
x_{\mathrm{next}}
=
\arg\max_x
\operatorname{Var}_H[\hat Y_H(t\mid x)]
\]

The system then recommends the location expected to separate the remaining explanations most strongly.

---

## 7. Required development order

### Gate A — Template integrity

- Validate graph and measurement schemas.
- Fit healthy residual basis from WaveCompare-aligned captures.
- Enumerate all connected attachment sites without model/location rules.
- Verify decomposition and score calculations.
- Keep the forward engine replaceable.

### Gate B — Researched seed library

For every seed family, document:

- governing equations or SPICE topology;
- parameter definitions and physical bounds;
- expected input/output ports;
- model order and complexity;
- assumptions and known failure cases;
- provenance.

No seed may be promoted from “demonstration” to “research-backed” without this record.

### Gate C — Controlled bench validation

Use a small known circuit with several probe points. Deliberately change one component or topology element at a time. Verify that:

- the correct model family ranks above wrong families;
- fitted effective parameters move in the correct direction;
- location information improves ranking;
- a second measurement collapses ambiguity;
- known normal noise is not mistaken for physical change.

### Gate D — Empirical statistical library

Collect repeated healthy measurements under controlled conditions and learn:

- nominal waveform;
- pointwise variation;
- normal residual modes;
- nuisance parameter distributions;
- operating-mode clusters.

### Gate E — Blind fault trial

Hide the inserted change from the inference process. Report ranked model families, parameter shifts, and graph regions. Do not claim exact component identification unless the experiment demonstrates identifiability.

---

## 8. Guardrails

1. The graph is a coarse connection map, not a complete schematic.
2. Seeds are location-agnostic; only connectivity constrains candidate sites.
3. Effective parameters are not automatically literal component values.
4. Physics seeds and empirical healthy statistics remain separate libraries.
5. A good waveform fit does not prove a unique physical explanation.
6. Every percentage confidence must be calibrated against held-out physical trials.
7. Maintenance changes require baseline versioning rather than permanent anomaly flags.
8. Simulation validates implementation; controlled hardware validates physical meaning.

---

## 9. Phase-1 output contract

Given graph \(G\), measurement context \(X\), input \(U\), observed waveform \(Y\), healthy baseline \(B_x\), and candidate hypotheses, the template returns:

\[
\left
\{
H_i,
J(H_i),
\hat Y_{H_i},
a_{H_i},
e_{\perp,H_i}
\right\}
\right._{i=1}^{N_H}
\]

sorted from lowest to highest score.

That is the container into which the researched seed library, SPICE backend, and real statistical library will be fitted in later phases.
