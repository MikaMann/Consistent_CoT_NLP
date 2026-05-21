"""
Generate reasoning traces for MR-Ben dataset (domains 11, 12, 13).
Uses the prompt from Figure 7 of MR-Ben paper (arXiv:2406.13975).
Queries a vllm server running the OpenAI-compatible API.
 
Usage:
    python generate_traces.py \
        --model_name meta-llama/Llama-3.1-8B-Instruct \
        --base_url http://localhost:8192/v1 \
        --domains 11 12 13 \
        --n_per_domain 10 \
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
# The paper uses this template to generate step-by-step CoT solutions for
# multiple-choice questions, which then serve as the "model solutions" to
# be meta-reasoned about.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a helpful assistant that solves multiple choice questions step by step. "
    "For each question, reason through it carefully and provide a detailed solution "
    "with numbered steps. End your response with 'The answer is X' where X is the "
    "letter of the correct option."
)
 
# Figure 7 user prompt template from MR-Ben paper
USER_PROMPT_TEMPLATE = """\
Please solve the following multiple choice problem step by step.
 
Problem: {question}
 
Options:
{options}
 
Please think step by step and provide your solution.\
"""
 
 
def format_options(options: dict | list) -> str:
    """Format options dict/list into lettered lines."""
    if isinstance(options, dict):
        return "\n".join(f"{k}. {v}" for k, v in options.items())
    elif isinstance(options, list):
        labels = "ABCDEFGHIJ"
        return "\n".join(f"{labels[i]}. {opt}" for i, opt in enumerate(options))
    return str(options)
 
 
def build_prompt(item: dict) -> str:
    question = item.get("Question", item.get("question", ""))
    options_raw = item.get("Options", item.get("options", {}))
    options_str = format_options(options_raw)
    return USER_PROMPT_TEMPLATE.format(question=question, options=options_str)
 
 
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
 
 
def get_subject_id(item: dict) -> int | None:
    """Extract numeric subject/domain id from a dataset item."""
    subject = item.get("Subject", item.get("subject", ""))
    if isinstance(subject, int):
        return subject
    if isinstance(subject, str) and subject.strip().lstrip("-").isdigit():
        return int(subject.strip())
    return None
 
 
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name", required=True,
                        help="Model id as registered in vllm (e.g. meta-llama/Llama-3.1-8B-Instruct)")
    parser.add_argument("--base_url", default="http://localhost:8192/v1",
                        help="Base URL of the vllm OpenAI-compatible server")
    parser.add_argument("--api_key", default="placeholder",
                        help="API key (any non-empty string for local vllm)")
    parser.add_argument("--domains", nargs="+", type=int, default=[11, 12, 13],
                        help="Domain/subject IDs to include (11=HS Bio, 12=Col Bio, 13=Col Med)")
    parser.add_argument("--n_per_domain", type=int, default=10,
                        help="Number of items to sample per domain")
    parser.add_argument("--output_file", required=True,
                        help="Output JSONL file path")
    parser.add_argument("--max_tokens", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
 
    random.seed(args.seed)
 
    client = OpenAI(base_url=args.base_url, api_key=args.api_key)
 
    print(f"Loading MR-Ben dataset...", flush=True)
    dataset = load_dataset("Randolphzeng/Mr-Ben", split="train")
 
    # Filter to target domains
    domain_set = set(args.domains)
    domain_buckets: dict[int, list] = {d: [] for d in args.domains}
 
    for item in dataset:
        sid = get_subject_id(item)
        if sid in domain_set:
            domain_buckets[sid].append(item)
 
    for d, items in domain_buckets.items():
        print(f"  Domain {d}: {len(items)} items available", flush=True)
        if len(items) < args.n_per_domain:
            print(f"  WARNING: only {len(items)} items for domain {d}, "
                  f"requested {args.n_per_domain}", flush=True)
 
    # Sample n_per_domain from each domain
    sampled = []
    for d in args.domains:
        pool = domain_buckets[d]
        n = min(args.n_per_domain, len(pool))
        sampled.extend(random.sample(pool, n))
 
    print(f"Total items to process: {len(sampled)}", flush=True)
 
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
                "domain": get_subject_id(item),
                "question_uuid": item.get("Question_UUID", item.get("question_uuid", f"item_{i}")),
                "question": item.get("Question", item.get("question", "")),
                "options": item.get("Options", item.get("options", {})),
                "ground_truth_answer": item.get(
                    "Ground_Truth_Answer_Modified",
                    item.get("Ground_Truth_Answer", item.get("ground_truth_answer", ""))
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