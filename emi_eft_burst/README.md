# emi_eft_burst

## Seed purpose

Electrical fast transient burst is an EMI seed for repetitive fast transients arriving in burst packets.

## What this folder should contain

- EFT/burst synthetic generator
- Victim-line capture CSVs
- Optional switching-source channel
- Burst-density and edge-count output

## Diagnostic markers

- Clustered fast spikes rather than one isolated spike
- Burst packets over microseconds to milliseconds
- Timing may correlate with relay, contactor, or inductive switching activity
- Broadband event energy

## Best Gamma/ElectroStat modules

- edge counting
- STFT
- wavelet
- event statistics

## Confidence rule

High confidence requires multiple spikes in burst packets and correlation with switching activity if a source channel exists. Low confidence if only one isolated spike exists.

## Not equivalent to

- pq_impulsive_transient
- slow contact bounce
- loose-probe artifact
