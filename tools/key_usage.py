#!/usr/bin/env python3
"""Print the key's total usage in USD (GET /key). The key is read from the environment only."""
import json, os, urllib.request
base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
req = urllib.request.Request(f"{base}/key", headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"})
print(json.load(urllib.request.urlopen(req))["data"]["usage"])
