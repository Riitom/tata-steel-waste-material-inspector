from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the AI-Assisted Scrap Detection And Weight Estimation web application.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    uvicorn.run(
        "waste_web.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(ROOT / "src"),
    )


if __name__ == "__main__":
    main()
