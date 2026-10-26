# Source preview publication review

The publication candidate is the explicit source allowlist in
`tools/package_developer_preview.py`. The working research directory is not the
publication set. In particular, do not publish the directory recursively.

## Licence and contents

- Newly authored source uses the root MIT licence selected by the owner.
- RTLPlayground-derived styling retains its original MIT notice and attribution.
  The standalone builder embeds both project and upstream licence material.
- Vendor WSP/GPHY binaries, bootloader images, extracted web assets and CLI help
  are excluded. Builders require separately supplied vendor firmware and the
  public verification-key record. No vendor-binary redistribution permission
  has been established by this project.
- Imported research-tool repositories and executables are excluded. Build-tool
  versions and the independently checked instruction fixtures are documented
  in BUILD.md.

## Privacy review of the source candidate

The allowlisted archive was inspected for private-key blocks, session cookies,
credentials, local user paths, email addresses, MAC addresses, raw backups and
captured configuration. No actual device MAC, personal email, local user path,
private key or session token was found. Synthetic test credentials are test
inputs, not captured device accounts. Default/example network addresses in code
are not a configuration backup.

The additional text scan produced two harmless matches: the JavaScript
identifier `keepSession=createSessionKeeper` resembled a cookie pattern, and
the packager's own private-key rejection expression contains the words
`PRIVATE KEY`. Neither contains a secret. No .bin, .log, .pem or .key member,
research capture directory, imported repository or programmer binary is allowed
into this archive.

The README includes ten individually reviewed desktop screenshots of the running
interface. Device names, IP/MAC addresses, contact details and module serial
numbers were anonymised before capture. The VLAN example is an unapplied draft;
the terminal shows only a read-only version query. Each approved PNG is explicitly
allowlisted and hash-pinned in the packager. Raw captures and mobile screenshots
remain excluded.

The package manifest hashes each included source and approved screenshot. These findings apply to the
reviewed allowlist, not future additions or a recursive workspace upload.
Regenerate and inspect the candidate after source changes; do not add firmware
or captured test fixtures simply to make a public test pass.

## Prepare a local repository candidate

From the research workspace or a previously extracted source tree:

```sh
python3 tools/package_developer_preview.py
python3 tools/prepare_github_repo.py --output-dir artifacts/github/mxl-playground
```

Choose a new output directory each time. The staging tool verifies every source
manifest hash, refuses unsafe/unlisted archive paths and checks local Markdown
links before creating the directory. It never copies the research workspace
recursively. Generated firmware used for local verification remains ignored
under `artifacts/` and is not in the archive. Private factory inputs belong
outside the candidate or in its ignored `input/` directory.

The staged README, build, installation, recovery, contribution and release-gate
documents form the proposed GitHub project. Review this tree before creating a
remote repository or publishing it; neither command commits or pushes files.

## Publication status and claims

The allowlisted source is being published as an experimental public GitHub
preview after private review. No firmware release has been published; see
[GITHUB.md](GITHUB.md) for the publication scope.
Its source-only build has been reproduced in a fresh directory with externally
supplied inputs; repeated builds were byte-identical. It is suitable for a
research/developer source preview, with the experimental installation and
recovery limitations in INSTALL.md retained.

It is not yet a generally supported firmware release. Linked optical tests, rejected-image fallback, exact SPI restoration and another
owner's independent installation remain hardware validation tasks. Management
VLAN is integrated; tagged-client and cold-power checks of the integrated build
remain open. A stock-to-custom first-install rehearsal is still required.

The source candidate now includes the full management runtime C sources, terminal
sources and a local repository staging tool. Staging verifies every manifest
hash and relative Markdown link before creating a new tree. It never initializes
Git, commits, creates a remote repository or uploads anything.
