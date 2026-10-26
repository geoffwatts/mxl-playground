# Source and attribution review

The UI's RTLPlayground-derived styling retains the upstream MIT licence and
copyright notice in `designs/mxl-management/LICENSE-RTLPlayground`; the standalone
HTML embeds a downloadable copy. The upstream project is
https://github.com/logicog/RTLPlayground , inspected revision
`41ed689ae0812839d468cb000e6301722f4d20ff`.

REA, Ghidra, Sony ARCv2 support, sks32kmon and other donor projects are research
or development tools/references. Their repositories, binaries and source trees
are not included in the source preview. TP-Link and GoodTop vendor firmware,
embedded web assets, extracted CLI help, certificates/private-key material and
raw captures are excluded. A locally built updater contains user-supplied
vendor code and must not be treated as a redistribution-approved binary.

Newly authored project source is MIT-licensed; see the root LICENSE. The owner
selected MIT for the public source release. This grant does not relicense vendor
firmware, imported tool trees, captures or third-party materials. Existing
third-party notices continue to apply independently. The public repository contains experimental source, not vendor firmware releases.

## Browser terminal

The repository includes the browser distributions of
[xterm.js](https://github.com/xtermjs/xterm.js) **6.0.0** and its **addon-fit
0.11.0**, under `designs/mxl-management/vendor/xterm/`. Both are MIT licensed;
their original notices are retained in `LICENSE-xterm` and `LICENSE-addon-fit`.
`provenance.json` records official npm tarball URLs, SHA-512 integrity values
and individual file hashes. No npm installation scripts are run.

The standalone builder verifies those files, embeds the JavaScript/CSS locally,
and includes downloadable licence text in the terminal toolbar. No MaxLinear or
TP-Link firmware is part of these third-party browser dependencies.
