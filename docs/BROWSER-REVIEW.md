# Native UI browser review — 25 October 2026

Chrome was operated through the Computer Use interface. The installed switch
and the loopback preview both used the real switch backend; no configuration
was applied through the browser during this review.

Observed on the installed inventory/SFP build:

- Native admin login succeeded, with the saved name and firmware displayed.
- Overview, VLANs and SFP pages rendered with the selected sidebar highlighted.
- Both empty cages showed unavailable measurements rather than invented zeros.

Observed on the updated loopback preview:

- Login succeeded against the native backend and sidebar navigation changed
  the hash route within the same app.
- VLAN membership column headings and editor headings align with their controls
  after correcting CSS selector specificity. Untagged/PVID indicators, separate
  SFP columns and the membership legend remain visible.
- The model label now uses the native status description, not a retail model
  literal. Before status is available it says Web Smart switch. The original
  GoodTop case label and the migrated firmware's SKS3200-8E2X description differ;
  the latter is a reported software string, not physical-board identification.
- A direct entry into a non-overview page exposed a missing initial identity
  read. The refresh path now reads identity if not yet cached, so the saved
  switch name does not depend on first visiting Overview.

Automated verification also passed: 42 JavaScript tests (including isolated DOM
interaction checks) and 48 Python tests. The subsequent branding/initial-identity
edits passed the three applicable native/live UI tests. A fresh source archive
reproduced byte-identical firmware output twice using external vendor/public-key
inputs; no private device backup or complete SPI output was required.

This is partial browser coverage. Real-browser session expiry/reconnect,
mobile layouts, a complete page sweep and all hardware write paths are not
established by the observations above. Browser-only checks do not establish
forwarding, optical diagnostics with a module or management-VLAN isolation.

The polished full-CLI asset was subsequently installed through the native
inactive-slot updater (slots 3/4). Its served login HTML matched SHA-256
`d2b637267acb37ef6e29f72a82d260549b9936c52388f252983dc88007c27ee6`.
UART showed DMA RX/TX startup, saved-name load and both image_ok flags. Native
login and preservation of original inventory were independently checked.

Separate validation logins displaced the browser session during the follow-up.
The owner reported a persistent session-expired message and then confirmed that
refreshing restored operation. Do not treat that as a completed expiry/reconnect
test or introduce competing validation logins while an owner is using the UI.

## Follow-up with restarted Chrome

Restarting Chrome restored agreement between screenshots, accessibility content
and the selected route. A fresh native browser login canonicalised login.html
to the root URL. All 22 installed routes then passed a real Chrome accessibility
and native-read sweep without detected session, transport or JSON errors. This
was navigation/read coverage, not a configuration-write sweep.

A temporary, unapplied location draft survived a visible keepalive check. With
the switch tab hidden for more than 316 seconds and no competing HTTP logins,
returning detected the real idle expiry. The draft stayed in its original form;
the reconnect dialog accepted the native credentials and preserved the draft.
Discard-and-refresh restored the original saved value. Explicit native logout
and a fresh login also returned successfully to the selected VLAN page.

At a 390-CSS-pixel responsive viewport, the identity form, navigation drawer and
VLAN editor remained usable. The matrix scrolled horizontally to both SFP
columns. Selecting tagged membership on port 10 changed only the local draft,
updated the summary and disabled its Assign PVID checkbox. Cancel restored the
original ten untagged memberships. No switch configuration was applied. Desktop
dark VLAN styling was inspected, light styling was restored, and browser Back
returned from STP to the VLAN route with matching content.

The private browser-page and session evidence is under ignored
`artifacts/inventory/browser-*.json`. Remaining validation concerns are hardware
write/readback/persistence coverage, physical modules, cold-power/recovery and
management-VLAN integration, rather than an unperformed first browser pass.
