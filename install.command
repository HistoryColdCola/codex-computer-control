#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec node codex-computer-control/scripts/install.js
