"""Check that your Gemini key works, and see which models it can use.

Run:  python check_gemini.py
Reads GEMINI_API_KEY (and optionally GEMINI_MODEL) from your .env file.
It never prints the whole key, only its last four characters, so you can tell
which key the program is really using.
"""
import os

import requests
from dotenv import load_dotenv

from tanda_agent import API_ROOT, DEFAULT_MODEL

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
model = os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
if not key:
    raise SystemExit("No GEMINI_API_KEY found. Add it to your .env file and save it.")

print(f"Key found, ending in ...{key[-4:]}")
print(f"Model setting: {model}\n")


def short_error(resp):
    try:
        text = resp.json().get("error", {}).get("message", "")
    except ValueError:
        text = resp.text
    return text.replace(key, "***")[:400]


# Step 1: ask Google which models this key can see.
r = requests.get(API_ROOT, headers={"x-goog-api-key": key}, params={"pageSize": 100}, timeout=30)
print(f"Step 1, list models: HTTP {r.status_code}")
if r.status_code != 200:
    print("Google said:", short_error(r))
    print("\nThe key is not working yet, so fix this before trying the app.")
    raise SystemExit(1)

names = sorted(
    m["name"].replace("models/", "")
    for m in r.json().get("models", [])
    if "generateContent" in m.get("supportedGenerationMethods", []) and "gemini" in m["name"]
)
print(f"This key can use {len(names)} Gemini models. A few:")
for n in names[:20]:
    print("   ", n)
print("(Which of these are FREE is shown in Google AI Studio, not here.)\n")

# Step 2: send one tiny question to the model we plan to use.
r = requests.post(
    f"{API_ROOT}/{model}:generateContent",
    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    json={"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ready"}]}]},
    timeout=60,
)
print(f"Step 2, test question to '{model}': HTTP {r.status_code}")
if r.status_code == 200:
    parts = r.json()["candidates"][0]["content"]["parts"]
    print("Gemini replied:", "".join(p.get("text", "") for p in parts).strip())
    print("\nEverything works. If the app still errors, restart it.")
else:
    print("Google said:", short_error(r))
    if r.status_code == 404:
        print("\nThat model name isn't available to this key. Pick one from the list above "
              "and set GEMINI_MODEL in .env.")
