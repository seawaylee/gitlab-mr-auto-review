import re

with open("tests/test_gitlab_client.py", "r") as f:
    content = f.read()

content = content.replace("def get(self, url, verify, timeout):", "def get(self, url, verify, timeout, params=None):")
with open("tests/test_gitlab_client.py", "w") as f:
    f.write(content)
