"""Render Fil configuration locally; never create provider resources."""

import argparse
import json
from pathlib import Path

from fil_shop.agent_config import TOOL_NAMES, build_config

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--voice-id", required=True)
for name in TOOL_NAMES:
    parser.add_argument("--" + name.replace("_", "-") + "-id", required=True)
parser.add_argument("--test-id", action="append", default=[])
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--llm", choices=["gemini-3.5-flash", "gpt-6-luna", "deepseek-v41-flash"], default="deepseek-v41-flash")
args = parser.parse_args()
config = build_config(llm=args.llm, voice_id=args.voice_id, test_ids=args.test_id,
                      tool_ids={name: getattr(args, name + "_id") for name in TOOL_NAMES})
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
print(f"Rendered {args.output}; no provider calls made.")
