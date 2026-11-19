#!/usr/bin/env python3
"""CI for this repository: lint must be clean and the tests in test_visible.py must pass."""
import subprocess
import sys

lint = subprocess.run([sys.executable, '-I', 'p922lint.py', 'module.py'], capture_output=True, text=True)
tests = subprocess.run([sys.executable, '-I', '-m', 'unittest', 'discover', '-v', '-s', '.', '-t', '.', '-p', 'test_visible.py'], capture_output=True, text=True)
print('== lint (p922lint) ==')
print(lint.stdout.strip())
print('== tests (test_visible.py) ==')
print((tests.stdout + tests.stderr).strip()[-2500:])
ok = lint.returncode == 0 and tests.returncode == 0
print('== CI %s ==' % ('PASSED' if ok else 'FAILED'))
sys.exit(0 if ok else 1)
