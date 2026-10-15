#!/bin/sh
set -eu
mkdir -p "$HOME/.local/share/codex-hands"
touch "$HOME/.local/share/codex-hands/STOP"
echo 'Codex 双手已暂停。'
