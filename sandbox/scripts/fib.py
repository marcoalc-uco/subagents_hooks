#!/usr/bin/env python3
"""Tiny script for the sandbox-runner agent to execute: prints fib(n)."""
import sys


def fib(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(f"fib({n}) = {fib(n)}")
