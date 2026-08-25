import sys
import asyncio
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')
from backend.agent import commerce_agent

async def main():
    print("Starting single prompt test...", flush=True)
    res = await commerce_agent.run_prompt("Show me all shoes in stock")
    print("Final Output:\n", res["response"], flush=True)
    print("Tool calls:", [t["name"] for t in res["tool_calls"]], flush=True)

if __name__ == "__main__":
    asyncio.run(main())
