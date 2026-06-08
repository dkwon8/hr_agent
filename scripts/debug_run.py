"""Quick debug script — runs ingestion + deterministic filter and prints details."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_openai import ChatOpenAI
from config.settings import RESUME_DIR, OPENAI_API_KEY, TARGET_LOCATIONS, GRADUATION_EARLIEST, GRADUATION_LATEST
from src.tools.resume_parser import parse_resumes_from_directory


async def main():
    llm = ChatOpenAI(model="gpt-5.4", api_key=OPENAI_API_KEY, temperature=0)
    candidates = await parse_resumes_from_directory(RESUME_DIR, llm)

    print(f"Target locations: {TARGET_LOCATIONS}")
    print(f"Graduation window: {GRADUATION_EARLIEST} to {GRADUATION_LATEST}")
    print(f"{'='*70}\n")

    for c in candidates:
        print(f"  {c.name}")
        print(f"    Location:        '{c.location}'")
        print(f"    Graduation:      '{c.graduation_date}'")
        print(f"    Degree level:    '{c.degree_level}'")
        print(f"    University:      '{c.university}'")
        print(f"    Skills:          {c.skills[:8]}...")
        print()


asyncio.run(main())
