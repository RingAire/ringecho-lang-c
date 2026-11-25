# RingEcho-Lang-C

A zero-dependency C implementation of the RingEcho compiler toolchain.

Compiles `.reo` source → C source → gcc → native binary. No LLVM, no external libraries required.

English | [简体中文](README.zh.md) | [繁體中文](README.zht.md)

<p align="center">
  <a href="https://github.com/RingAire/ringecho-lang-c/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/RingAire/ringecho-lang-c/ci.yml?branch=main&label=ci&style=flat-square" alt="CI status"></a>
  <a href="https://github.com/RingAire/ringecho-lang-c/releases"><img src="https://img.shields.io/github/v/release/RingAire/ringecho-lang-c?label=release&style=flat-square" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-1A73E8?style=flat-square" alt="Apache-2.0 license"></a>
  <img src="https://img.shields.io/badge/language-C-555555?logo=c&logoColor=white&style=flat-square" alt="C">
  <img src="https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-4B5563?style=flat-square" alt="Windows, macOS and Linux">
  <a href="https://github.com/RingAire/ringecho-lang-c/stargazers"><img src="https://img.shields.io/github/stars/RingAire/ringecho-lang-c?label=stars&style=flat-square" alt="GitHub stars"></a>
</p>

## Status

| Item | Value |
|------|-------|
| Version | 0.4.0 |
| Tests | Passing (make test) |
| Toolchain | 2 binaries: `rev` / `rem` (`rvm` is a separate project) |
| Backends | C source, freestanding C, reo ISA, shared library, WebAssembly (WASI) |
| License | Apache-2.0 |

## Toolchain

An experimental `--backend native` emits x86-64 machine code and ELF64 objects
directly, using the system linker for Linux executables without invoking a C
compiler. It currently supports 8–64-bit integers, floats, booleans and byte characters; see
[NATIVE.md](NATIVE.md) for commands, supported features and limitations.
The full type/layout migration is tracked in [TYPE_SYSTEM.md](TYPE_SYSTEM.md).

| Binary | Role | Description |
|--------|------|-------------|
| `rev` | Compiler / evaluator | Compile, run, type-check, LSP server, project init, venv |
| `rem` | Package manager | Install/list/remove/search packages (npm-like) |
| `rvm` | Version manager (separate repo) | [RingAire/rvm](https://github.com/RingAire/rvm) installs released compiler versions |

## Build

```bash
make CONFIG=Release build
```

| Profile | Flags |
|---------|-------|
| Release | `-O3 -DNDEBUG` |
| Debug | `-O0 -g3` |
| Alpha | `-O2 -g` |

Requires a C11 compiler (gcc/clang) with pthread support. See [BUILD.md](BUILD.md) for platform matrix.

## Usage

### rev — compiler

```bash
rev run <file.reo> [--target c|reo|c-freestanding]  # Compile and run
rev build <file.reo> [-o out]                       # Compile to executable/asm
rev build <file.reo> --shared                       # Compile to shared library (.so/.dll)
rev build <file.reo> --target wasm                  # Compile to WebAssembly (WASI)
rev build                                           # Build project (reads ringecho.toml)
rev check <file.reo>                                # Type check only
rev lsp                                             # Start LSP server
rev venv <init|activate>                            # Manage virtual environment
rev init [name]                                     # Create new project
rev clean                                           # Remove build artifacts
```

`rev init` scaffolds a project with `main.reo`, `ringecho.toml`, `.gitignore` and a `.renv/` virtual environment. Argumentless `rev build` reads the entry point from `ringecho.toml` and outputs to `target/Release/`.

### rem — package manager

```bash
rem init [name]        # Initialize new project
rem install <pkg>      # Install a package
rem list               # List installed packages
rem remove <pkg>       # Remove a package
rem update             # Update dependencies
rem search <query>     # Search packages
rem publish            # Publish current package
```

### rvm — version manager (separate project)

`rvm` now lives in [RingAire/rvm](https://github.com/RingAire/rvm). It installs
released compiler versions from `https://ringecho-lang.org/dist` (GitHub
Releases fallback) and is versioned and released independently.

## Features

- Full type system (i8-i128, u8-u128, f32/f64, bool, char, str)
- Struct, Enum, Trait + impl + static method dispatch
- Generic functions + structs with lazy monomorphization
- Option/Result + `?` operator
- Lambda/closures (no capture yet)
- Match expressions (integer, float, bool, char, string content + enum tag; typed scalar results)
- Pipeline operator `|>`
- Component keyword
- Kernel attributes: `@align` on statics/functions/fields, `@no_mangle`/`@export_name`, `@noreturn`; `extern` linker variables
- Layout/portability: fieldless enum `@repr(C|u8|u16|u32|u64)`, field-level `@align`, `@cfg(target_arch=...)`/`@cfg(kernel|hosted|debug_assertions)`
- Kernel syntax: `unsafe fn`/`unsafe { }`, `asm("...")` templates and `@naked` functions
- for-in range + string iteration
- spawn/await concurrency (pthread)
- GC: 3 modes (none/auto/manual). `none` leaves strings untracked; `manual`
  exposes `gc_retain`/`gc_release` (`gc_add_root`/`gc_remove_root` are
  aliases) for explicit ownership; `auto` collects at a threshold but the
  compiler-side automatic retain/release pass is not implemented yet.
- LSP server: JSON-RPC + diagnostics
- Multi-file modules (import with recursive resolution)
- extern C FFI
- External arbitrary-precision integers (`libs/bigint/`, see below)
- Conditional compilation with `@cfg(windows|macos|linux)` on top-level declarations
- char type with full escape support
- Virtual environments (`.renv/`) with bundled stdlib (`std::io`, `std::math`, `std::string`, `std::vec`)
- Project configuration via `ringecho.toml`

## External big integers

Primitive integers end at 128 bits. Big integers are supplied as an external C
library rather than a language feature, bound through the FFI channel
(`extern` declarations plus `--include` / `--lib-dir` / `--link`), with values
carried as opaque `u64` handles:

```bash
make test-bigint
# equivalent:
rev run libs/bigint/demo_bigprime.reo --lib-dir libs/bigint/build --link reo_bigint
```

The demo loads a 768-bit prime, shows it has no factor below one million, and
self-checks subtraction and multiplication — all past the native range. See
[libs/bigint/README.md](libs/bigint/README.md).

## Testing

`match` evaluates its subject once and executes only the first matching arm.
Patterns must be assignable to the subject type; arm results must be assignable
to the first arm's type. A wildcard `_` must be last. Exhaustiveness is not yet
checked: unmatched numeric results default to zero and string results to the
empty string. Prefer an explicit wildcard arm.

Run output-asserting match regressions with `make CONFIG=Release test-match`
(requires Python 3).

```bash
make CONFIG=Debug test          # End-to-end: compile + run all positive tests,
                                # verify expected failures (sema/syntax/runtime)
make test-one FILE=tests/hello.reo   # Run a single test
make check-one FILE=tests/hello.reo  # Type-check a single test
make test-list                       # List all tests
```

## License

[Apache-2.0](LICENSE) - Copyright (c) 2025-2026 辉夜铃 (KaguyaRing) & Ringaire

## Star History

<a href="https://www.star-history.com/#RingAire/ringecho-lang-c&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=RingAire/ringecho-lang-c&amp;type=Date&amp;theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=RingAire/ringecho-lang-c&amp;type=Date" />
    <img src="https://api.star-history.com/svg?repos=RingAire/ringecho-lang-c&amp;type=Date" alt="Star History Chart" />
  </picture>
</a>
