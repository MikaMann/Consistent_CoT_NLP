#!/bin/bash
#SBATCH --job-name=mrben_llama3
#SBATCH --partition=gpushort
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=04:00:00
#SBATCH --gres=gpu:a100:1
#SBATCH --output=logs/llama3_%j.out
#SBATCH --error=logs/llama3_%j.err

set -e

MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"
PORT=8192
OUTPUT="outputs/llama3_8b_traces.jsonl"

mkdir -p logs outputs

# ---- Environment ----
module load EESSI/2025.06
module load Python/3.13.5-GCCcore-14.3.0
source .env/bin/activate

# ---- Serve vllm in background ----
export HF_HOME=/scratch/$USER/hf_cache
mkdir -p $HF_HOME

echo "Starting vllm server for $MODEL_NAME on port $PORT..."
vllm serve "$MODEL_NAME" \
    --download-dir "$HF_HOME/models" \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.90 \
    --port "$PORT" \
    --disable-log-requests &
VLLM_PID=$!

# Wait for server to be ready
echo "Waiting for vllm server to start..."
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
        echo "vllm server is ready."
        break
    fi
    sleep 5
    if [ $i -eq 60 ]; then
        echo "ERROR: vllm server did not start in time." >&2
        kill $VLLM_PID 2>/dev/null
        exit 1
    fi
done

# ---- Generate traces ----
python scripts/generate_traces.py \
    --model_name "$MODEL_NAME" \
    --base_url "http://localhost:${PORT}/v1" \
    --domains 11 12 13 \
    --n_per_domain 10 \
    --output_file "$OUTPUT" \
    --max_tokens 1024 \
    --seed 42

# ---- Cleanup ----
kill $VLLM_PID 2>/dev/null || true
echo "Job complete. Output: $OUTPUT"