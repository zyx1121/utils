#!/usr/bin/env bash
# Regression fixture — a direct child that just hangs, no subprocess of its
# own. Proves the timeout+grace fix doesn't regress the ordinary case:
# killing a well-behaved hung atom should resolve near timeoutMs, not wait
# out the full EXEC_GRACE_MS window. `exec` replaces this process's image
# with `sleep` directly — no fork, no grandchild, no fd-inheritance issue.
exec sleep 999999
