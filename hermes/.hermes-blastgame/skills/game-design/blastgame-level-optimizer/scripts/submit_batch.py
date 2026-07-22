#!/usr/bin/env python3
"""Submit multiple levels in one batch. Patch all → submit once → wait for all to complete.
Reads probe configs from D:/download/Hermes/tools/probe_configs.json.
Auto-evaluates after completion using find_best_combo.py.

Usage: python submit_batch.py '89,90,91' [--games 400] [--tag mytag]
"""
# Canonical version lives at: D:/download/Hermes/scripts/submit_batch.py
# This is a convenience copy. Refer to the canonical version for latest updates.
import sys, os
sys.path.insert(0, r"D:\download\Hermes")
SCRIPT = r"D:\download\Hermes\scripts\submit_batch.py"
if os.path.exists(SCRIPT):
    # Delegate to canonical version
    import subprocess
    subprocess.run([sys.executable, SCRIPT] + sys.argv[1:])
else:
    print(f"Canonical script not found: {SCRIPT}")
    print("Run directly: python D:/download/Hermes/scripts/submit_batch.py ...")
    sys.exit(1)
