# GitHub source preview

The first repository is `geoffwatts/mxl-playground`, initially private for review.
It contains the source allowlist, not the complete research workspace. There
is no firmware release or tag yet. Newly authored code uses MIT; upstream notices
remain intact.

## Before making it public

1. Check README.md, BUILD.md, SERIAL-INSTALLER.md and RECOVERY.md as a new owner.
   Preserve the programmer requirement and experimental installation limits.
2. Require passing source checks. They verify the manifest, exact tracked files,
   documentation links, UART/installer failure paths and frontend source, and
   rebuild the UI and instruction-plan extensions without vendor firmware.
3. Review the source and attribution, then share a research/developer preview.
   Do not present it as a generally supported firmware release. The remaining
   hardware gates in ROADMAP.md stay open.

CI does not access a switch or vendor image, upload firmware, run hardware writes,
or validate recovery. Firmware-dependent tests skip without private inputs; the
terminal DOM test additionally needs the optional local JSDOM dependency. The
compiled C extensions were reproduced locally; this initial CI does not compile
them. Those omissions must remain visible in test results and release claims.

## Updating the preview

Make changes in the source workspace, regenerate the allowlisted archive and
stage it into a new directory using REVIEW.md. Review the diff against the Git
repository before committing. The committed source manifest must be regenerated
after source changes; `python3 tools/check_source_tree.py --git` checks exact
tracked-file membership as well as hashes. Generated images and captures remain
private and ignored. Never recursively copy or commit the research directory.

A source commit is separate from a firmware release. Do not upload locally built
WSP/GPHY, SPI backups or binary deltas as GitHub assets. A later public source
preview can use this same private repository after an explicit visibility change.
