#!/bin/bash
# Run this ONCE on an interactive node to set up the virtual environment.
# ssh pnumber@interactive1.hb.hpc.rug.nl
# Then: bash scripts/setup.sh

set -e

module load EESSI/2025.06
module load Python/3.13.5-GCCcore-14.3.0

if [ ! -d ".env" ]; then
    python3 -m venv .env
    echo "Created virtual environment."
fi

source .env/bin/activate
pip install --upgrade pip wheel
pip install vllm
pip install datasets openai

echo ""
echo "Setup complete. Run jobs with:"
echo "  sbatch scripts/run_llama3.sh"
echo "  sbatch scripts/run_qwen25.sh"
echo "  sbatch scripts/run_qwen3.sh"