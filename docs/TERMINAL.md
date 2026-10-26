# Browser terminal

Open **Terminal & CLI**, read the warning, then choose **I understand — open
terminal**. No terminal session or input is sent before that acknowledgement.
The warning stays above the open terminal. Revisit the page to see the gate
again. Connect/disconnect controls manage the browser attachment.

This is the real Zephyr UART shell. It is unrestricted: commands can overwrite
flash or RAM, erase settings, crash the switch or prevent boot. Recovery may
require an SPI programmer. It shares input, output, command history and line
editing with the physical serial console; avoid typing from both at once.

Click the terminal and type directly; there is no separate command-entry box.
The browser uses **xterm.js 6.0.0** with ANSI colours, a visible cursor, selection,
2,000 lines of scrollback, automatic fitting and an **Expand terminal** control.
Tab completes commands, Up/Down recall native history, Backspace edits and Ctrl-C
behaves as it does over UART. Shift-Tab moves focus out; browser Command-key
shortcuts remain available. Copy selection also has a toolbar button.

Use **Clear view** to reset the display and redraw the native command line.
Disconnecting does not undo a command or clear the UART input line. Paste is
bounded to the remaining 4 KiB input queue; an oversized paste is rejected
rather than partially queued. Multiline paste can execute commands immediately.
For a first read-only check, run `kernel version` or `help`. Native settings
changes may require **Save configuration**.

The browser emulator resizes with its pane. If Zephyr's line editor still wraps
at its previous width, run the native `resize` command to let it query the new
terminal dimensions. No shell command is silently executed on browser resize.
Ctrl-C does not forcibly abort a synchronous firmware command that the native
UART shell cannot interrupt. Full terminal emulation does not add Linux tools,
a new shell or applications to WSP.

Terminal libraries and CSS are bundled locally with their MIT notices. The
standalone UI stores its JavaScript compressed and unpacks it in the browser,
keeping the whole interface within the existing flash asset region. No CDN or
runtime dependency download is needed. A current browser with
`DecompressionStream('gzip')` and JavaScript modules is required. Terminal output
is written to the emulator as text/control sequences, never inserted as HTML;
terminal hyperlinks are disabled and no clipboard-write addon is installed.

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
operation and mirroring. The installed xterm.js pane was checked on the switch
with direct typing, Backspace, native history and Tab, Ctrl-C followed by
`kernel version`, and expanded/collapsed sizing. The browser fixture also checks
raw arrow/control sequences and multiline paste at 1440 pixels, without
JavaScript exceptions or page-width overflow. The switch rebooted and the
served UI hash matched; its saved configuration remained byte-identical.

After 100 polls, native malloc allocation remained 27,548 bytes (about 36 KiB
free); observed worker stack high-water was 4840/6144 and UART shell 1000/2176
bytes. These are observations for the tested workload, not worst-case limits.
Ring overwrite, counter wrap and input backpressure are covered by a compiled
C fixture with address/undefined-behavior sanitizers. Host DOM tests cover
the warning gate, raw input forwarding, bounded paste, lifecycle cleanup and
stopping after uncertain input. Source tests verify compressed JavaScript
round trips, dependency integrity and the existing asset-size limit. No destructive console command was used for
these checks.

The exact-build builder admits only the pinned terminal extension and verifies
that it does not overlap the HTML asset. Boot records, GPHY and settings layout
are untouched. Private device transcripts remain excluded from publication.
