# compiler-reo

A RingEcho implementation of the RingEcho compiler (self-hosting), written in
`.reo` and built with the C reference compiler (`rev0`) during bootstrap.
See [BOOTSTRAP.md](../BOOTSTRAP.md) for the executed gates and remaining work.

Stage: seed. Files:
- `lexer.reo` — tokenizes a source string and self-checks the result.
- `parser.reo` — `ident = number;` parsing seed.
- `expr.reo` — expression AST, precedence climbing, evaluator.
- `frontend.reo` — statements/blocks, `if`/`else`, `while`, assignments, enums,
  function declarations with parameter/return types, a deterministic AST dump,
  scoped lexical name resolution, and initial type checking. Its self-check
  includes a first self-consumption probe: it parses and resolves `lexer.reo`
   with zero errors.
- `state.reo` — shared token/AST storage and resource limits, owned by the driver.
- `types.reo` — structural pointer/reference/array/slice/tuple/function/generic
  type parsing, canonical printing and identity; no placeholder erasure.
- `declarations.reo` — struct/untagged union/type-alias declaration parsing.
- `type_tests.reo` — executed type/declaration roundtrip and rejection checks.

Run one: `target/Release/rev run compiler-reo/frontend.reo`.
Run all: `make test-selfhost`.

`make test-selfhost-types PYTHON=python` additionally builds the frontend and
executes external CLI tests and deterministic grammar/hostile-token fuzzing.
The compiled frontend accepts `--type 'fn(*const u8, usize) -> u128'` and prints
the canonical type, or exits 1 with diagnostics. With no arguments it runs the
self-checks. This is a frontend bootstrap, not yet a compiler that emits code.
