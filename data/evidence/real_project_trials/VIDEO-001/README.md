# VIDEO-001 — Multicam synchronization edge cases

Both conditions started from clawd commit `a653637` and used generated media
only. Harness alone received the released high-complexity protocol and verifier.

Initial implementations passed 11 focused tests, but blind review found missing
valid screen+face end-to-end proof. Harness also regressed single-camera
compatibility, used a fixed atomic temp name, and left mismatched-rate windowed
sync weaker. Both entered acceptance repair. The original condition agents then
hit a platform usage limit; their worktrees were preserved and independent
replacement agents resumed only their assigned condition.

Final sequential evaluation passed control 86/86 and harness 87/87. Earlier
parallel full-suite runs were killed by a pre-existing test that allocates about
20 minutes of 16 kHz float audio; the same test passed sequentially in both
conditions. Blind review selected control 4.6/5 versus harness 3.9/5 for stronger
real reconstruction/PiP, explicit status taxonomy, and windowed-resampling
evidence.

Frozen wall-clock duration includes the roughly 14.5-hour platform quota pause,
so this pair materially increases the reported mean duration. The pause is not
removed or reconstructed.
