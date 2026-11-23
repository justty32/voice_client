#!/usr/bin/env bash
# Project-owned check; wf-lint passes project root and strict flag.
exec python3 "$(dirname "$0")/index_check_local.py" "${1:-.}"
