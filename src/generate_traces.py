"""
Generate reasoning traces for MR-Ben dataset.
Uses the prompt from Figure 7 of MR-Ben paper (arXiv:2406.13975).
Queries a vllm server running the OpenAI-compatible API.

Usage:
    python generate_traces.py \
        --model_name meta-llama/Llama-3.1-8B-Instruct \
        --base_url http://localhost:8192/v1 \
        --subject college_medicine \
        --n_samples 10 \
        --output_file outputs/llama3_traces.jsonl \
        --seed 42
"""

import argparse
import json
import random
import sys
from pathlib import Path

from datasets import load_dataset
from openai import OpenAI

# ---------------------------------------------------------------------------
# MR-Ben Figure 7 prompt template
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a helpful assistant that solves multiple choice questions step by step. "
    "For each question, reason through it carefully and provide a detailed solution "
    "with numbered steps. End your response with 'The answer is X' where X is the "
    "letter of the correct option."
)

USER_PROMPT_TEMPLATE = """\
Please solve the following multiple choice problem step by step.

Problem: {question}

Options:
{options}

Please think step by step and provide your solution."""


def format_options(options) -> str:
    if isinstance(options, dict):
        return "\n".join(f"{k}. {v}" for k, v in options.items())
    elif isinstance(options, list):
        labels = "ABCDEFGHIJ"
        return "\n".join(f"{labels[i]}. {opt}" for i, opt in enumerate(options))
    return str(options)


def build_prompt(item: dict) -> str:
    question = item.get("Question", item.get("question", ""))
    options_raw = item.get("Options", item.get("options", {}))
    return USER_PROMPT_TEMPLATE.format(
        question=question,
        options=format_options(options_raw)
    )


def query_model(client: OpenAI, model_name: str, user_prompt: str, max_tokens: int = 1024) -> str:
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    return response.choices[0].message.content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name", required=True)
    parser.add_argument("--base_url", default="http://localhost:8192/v1")
    parser.add_argument("--api_key", default="placeholder")
    parser.add_argument("--subject", default="college_medicine",
                        help="Subject string as it appears in the dataset, e.g. college_medicine")
    parser.add_argument("--n_samples", type=int, default=10,
                        help="Number of questions to sample")
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--max_tokens", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    print("Loading MR-Ben dataset...", flush=True)
    dataset = load_dataset("Randolphzeng/Mr-Ben", split="train")

    # Print all unique subjects so you can verify the exact string
    all_subjects = set(row["Subject"] for row in dataset)
    print(f"Available subjects: {sorted(all_subjects)}", flush=True)

    pool = [row for row in dataset if row["Subject"] == args.subject]
    print(f"Found {len(pool)} items for subject '{args.subject}'", flush=True)

    if len(pool) == 0:
        print("ERROR: No items found. Check --subject matches one of the available subjects above.")
        sys.exit(1)

    if len(pool) < args.n_samples:
        print(f"WARNING: only {len(pool)} items available, requested {args.n_samples}", flush=True)

    sampled = random.sample(pool, min(args.n_samples, len(pool)))
    print(f"Sampled {len(sampled)} questions. Starting generation...", flush=True)

    Path(args.output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(args.output_file, "w") as f:
        for i, item in enumerate(sampled):
            user_prompt = build_prompt(item)
            print(f"[{i+1}/{len(sampled)}] Querying model...", flush=True)

            try:
                trace = query_model(client, args.model_name, user_prompt, args.max_tokens)
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                trace = f"ERROR: {e}"

            record = {
                "model": args.model_name,
                "subject": item.get("Subject"),
                "question_uuid": item.get("Question_UUID", f"item_{i}"),
                "question": item.get("Question", ""),
                "options": item.get("Options", {}),
                "ground_truth_answer": item.get(
                    "Ground_Truth_Answer_Modified",
                    item.get("Ground_Truth_Answer", "")
                ),
                "system_prompt": SYSTEM_PROMPT,
                "user_prompt": user_prompt,
                "model_trace": trace,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()

    print(f"Done. Saved {len(sampled)} traces to {args.output_file}", flush=True)


if __name__ == "__main__":
    main()