#!/usr/bin/env python3
"""CI for this repository: lint must be clean, the tests in test_visible.py must pass, and contract_check must report no
handler that swallows an exception the docstring says must be raised."""
import subprocess
import sys

lint = subprocess.run([sys.executable, '-I', 'p922lint.py', 'module.py'], capture_output=True, text=True)
tests = subprocess.run([sys.executable, '-I', '-m', 'unittest', 'discover', '-v', '-s', '.', '-t', '.', '-p', 'test_visible.py'], capture_output=True, text=True)
contract = subprocess.run([sys.executable, '-I', 'contract_check.py', 'module.py'], capture_output=True, text=True)
print('== lint (p922lint) ==')
print(lint.stdout.strip())
print('== tests (test_visible.py) ==')
print((tests.stdout + tests.stderr).strip()[-2500:])
print('== contract (contract_check) ==')
print((contract.stdout + contract.stderr).strip()[-1500:])
ok = lint.returncode == 0 and tests.returncode == 0 and contract.returncode == 0
print('== CI %s ==' % ('PASSED' if ok else 'FAILED'))
sys.exit(0 if ok else 1)
