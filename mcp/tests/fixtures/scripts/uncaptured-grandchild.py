#!/usr/bin/env python3
"""Regression fixture — mirrors scripts/mac-app.py's pre-fix bug (a reviewer
repro template): spawns a long-lived grandchild WITHOUT capturing its
output. The grandchild inherits this process's stdout/stderr file
descriptors — the same pipes the MCP executor reads to EOF — so killing
THIS process does not close the pipe; the orphaned grandchild still holds
the write end open. Exercises lib/exec.ts's grace-timeout fix
(EXEC_GRACE_MS): the executor must give up and return partial output
instead of waiting out the grandchild's full lifetime.
"""
import subprocess
import sys
import time

print("parent: spawning uncaptured grandchild")
subprocess.Popen(["sleep", "8"])  # deliberately uncaptured — inherits our stdio
sys.stdout.flush()
time.sleep(30)  # stay alive well past any reasonable timeoutMs; the executor kills us
