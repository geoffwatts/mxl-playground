# Browser terminal

Open **Terminal & CLI**, read the warning, then choose **I understand — open
terminal**. No terminal session or input is sent before that acknowledgement.
The warning stays above the open terminal. Revisit the page to see the gate
again. Connect/disconnect controls manage the browser attachment.

This is the real Zephyr UART shell. It is unrestricted: commands can overwrite
flash or RAM, erase settings, crash the switch or prevent boot. Recovery may
require an SPI programmer. It shares input, output, command history and line
editing with the physical serial console; avoid typing from both at once.

Click the dark terminal to type. Tab completes commands, Up/Down recall native
history, Backspace edits, and Ctrl-C behaves as it does over UART. Shift-Tab
leaves the terminal. The command field and Tab/Ctrl-C/Redraw buttons also work
on touch devices. For a first read-only check, run `kernel version` or `help`.
Native settings changes may require **Save configuration**.

The terminal view uses an 80-column VT100 line-editing renderer, with bounded
scrollback and plain-text output. It does not interpret output as HTML or
support every full-screen terminal application. Ctrl-C does not forcibly abort
a synchronous firmware command that the native UART shell cannot interrupt.
Disconnecting the browser does not undo a command or clear the UART line.

## Implementation and validation

The authenticated `/console.json` route feeds a 512-byte input queue into the
existing UART transport and mirrors successfully written output into a 4096-byte
ring. Execution stays on the native shell thread, preserving its parser,
handlers, argument checks and history. The physical UART remains connected.
There is no additional shell, worker thread, SSH server or Telnet server.

An attachment uses a browser-generated 16-byte nonce and the authenticated
session cookie. A new attachment replaces the previous one. Input requests
carry strictly increasing sequence numbers; duplicates and wrong owners are
rejected. The browser never automatically retries input after an ambiguous
response. Slow readers receive explicit output-loss indication. The small
polling buffer is for transferring output, not a separate command dispatcher.

The backend is 1900 compiled bytes, plus a registration wrapper, and uses about
4.7 KiB of boot-lifetime storage. All 584 planned instruction lengths were
independently decoded. Hardware tests passed HTTP command execution, native
Backspace/history/Tab, Ctrl-C followed by another command, wrong-nonce and
duplicate-input rejection, anonymous/malformed/method rejection, physical UART
operation and mirroring. Browser command execution and 1280/390-pixel layouts
passed without JavaScript exceptions or page-width overflow.

After 100 polls, native malloc allocation remained 27,548 bytes (about 36 KiB
free); observed worker stack high-water was 4840/6144 and UART shell 1000/2176
bytes. These are observations for the tested workload, not worst-case limits.
Ring overwrite, counter wrap and input backpressure are covered by a compiled
C fixture with address/undefined-behavior sanitizers. Host DOM tests cover
the warning gate, keyboard mapping, safe text rendering and stopping after
uncertain input. No destructive console command was used for these checks.

The exact-build builder admits only the pinned terminal extension and verifies
that it does not overlap the HTML asset. Boot records, GPHY and settings layout
are untouched. Private device transcripts remain excluded from publication.
