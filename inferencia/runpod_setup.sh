#!/usr/bin/env bash
set -euo pipefail

apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0
rm -rf /var/lib/apt/lists/*

if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

uv venv --python 3.12 --system-site-packages .venv
source .venv/bin/activate

uv pip install -r requirements.txt

python -c "import torch; print('cuda_available:', torch.cuda.is_available())"
python descargar_modelos.py
python diagnostico.py
