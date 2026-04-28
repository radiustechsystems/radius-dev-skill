# Radius Skills Agent Guide

This repo separates portable agent capabilities from deterministic runtime code.

Use these boundaries:

- `skills/`: portable instructions and references. Do not add host-specific runtime assumptions here.
- `spec/`: shared contracts for networks, tool schemas, and golden behavior tests.
- `runtime/`: deterministic implementations of the shared tool surface.
- `adapters/`: thin framework packaging and glue. Adapters should call a runtime instead of re-implementing wallet logic.

Before adding a capability, decide whether it is skill guidance, shared runtime behavior, or adapter-specific integration.

