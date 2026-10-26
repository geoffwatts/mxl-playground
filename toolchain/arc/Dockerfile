# Isolated build tools only; no vendor images or workspace files are copied.
# Official Debian bookworm-slim amd64 child of the recorded multi-platform index.
FROM debian@sha256:ec31d744f83f4a73447ba045aaab9409997efe5cc706eca4890c1be36cc1606a
RUN apt-get update -qq \
 && apt-get install -y --no-install-recommends \
      gcc-12-arc-linux-gnu=12.2.0-13cross1 binutils-arc-linux-gnu=2.40-2 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
