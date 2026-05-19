#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
        then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

if [[ ! -x ".venv/bin/python" ]]; then
    python_bin="$(find_python)" || {
        echo "Python 3.11+ nao encontrado. Instale python3 e python3-venv na VM." >&2
        exit 1
    }
    "$python_bin" -m venv .venv
fi

if [[ ! -f ".venv/.requirements.stamp" || "requirements.txt" -nt ".venv/.requirements.stamp" ]]; then
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
    touch .venv/.requirements.stamp
fi

if [[ "${1:-}" == "--prepare-only" ]]; then
    exit 0
fi

exec .venv/bin/python main.py
