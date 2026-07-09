# Test plan

1. Unit-test profile persistence, JSON argument parsing, and resource registration.
2. Exercise the installed `cli-anything-consul` command through Click's runner.
3. Against a live local instance, verify health, capability detection, and a reversible
   settings write over HTTP without leaving synthetic participation records.
4. Exercise Munich project creation, activation, and phase creation inside a Rails
   transaction that is rolled back after assertions.
5. Confirm the same generic surface against upstream CONSUL when its bridge is installed.
