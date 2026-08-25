import asyncio
import os
import time
from dotenv import load_dotenv
load_dotenv()
from groq import Groq

def test():
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))  # Set in .env
    t0 = time.time()
    print("Sending request to Groq openai/gpt-oss-120b...", flush=True)
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": "What is the capital of France? Answer in one word."}],
        max_tokens=50
    )
    print(f"Received in {time.time() - t0:.2f}s: {resp.choices[0].message.content}", flush=True)

if __name__ == "__main__":
    test()
