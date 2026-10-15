#!/bin/sh
set -eu
mkdir -p "$HOME/.local/share/codex-computer-control"
touch "$HOME/.local/share/codex-computer-control/STOP"
echo 'Codex 电脑控制已暂停。'
