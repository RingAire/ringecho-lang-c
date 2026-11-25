# RingEcho-Lang-C

RingEcho 编译器工具链的零依赖 C 实现。

将 `.reo` 源码 → C 源码 → gcc → 原生二进制。无需 LLVM，无需任何外部库。

[English](README.md) | 简体中文 | [繁體中文](README.zht.md)

<p align="center">
  <a href="https://github.com/RingAire/ringecho-lang-c/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/RingAire/ringecho-lang-c/ci.yml?branch=main&label=ci&style=flat-square" alt="CI 状态"></a>
  <a href="https://github.com/RingAire/ringecho-lang-c/releases"><img src="https://img.shields.io/github/v/release/RingAire/ringecho-lang-c?label=release&style=flat-square" alt="最新版本"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-1A73E8?style=flat-square" alt="Apache-2.0 许可证"></a>
  <img src="https://img.shields.io/badge/language-C-555555?logo=c&logoColor=white&style=flat-square" alt="C">
  <img src="https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-4B5563?style=flat-square" alt="Windows、macOS 与 Linux">
  <a href="https://github.com/RingAire/ringecho-lang-c/stargazers"><img src="https://img.shields.io/github/stars/RingAire/ringecho-lang-c?label=stars&style=flat-square" alt="GitHub Star 数"></a>
</p>

## 状态

| 项目 | 值 |
|------|-----|
| 版本 | 0.4.0 |
| 测试 | 通过（make test） |
| 工具链 | 2 个二进制：`rev` / `rem`（`rvm` 为独立项目） |
| 后端 | C 源码、freestanding C、reo ISA、共享库、WebAssembly (WASI) |
| 许可证 | Apache-2.0 |

## 工具链

新增实验性原生后端：`--backend native` 直接生成 x86-64 机器码和 ELF64
目标文件，通过系统链接器生成 Linux 可执行程序，不调用 C 编译器。
当前支持 8–64 位整数、浮点、布尔与字符子集，使用方式与边界见 [NATIVE.md](NATIVE.md)。
完整类型系统与系统级布局迁移状态见 [TYPE_SYSTEM.md](TYPE_SYSTEM.md)。

| 二进制 | 角色 | 说明 |
|--------|------|------|
| `rev` | 编译器 / 求值器 | 编译、运行、类型检查、LSP 服务器、项目初始化、虚拟环境 |
| `rem` | 包管理器 | 安装 / 列出 / 移除 / 搜索包（类 npm） |
| `rvm` | 版本管理器（独立仓库） | [RingAire/rvm](https://github.com/RingAire/rvm) 安装已发布的编译器版本 |

## 构建

```bash
make CONFIG=Release build
```

| 配置 | 编译标志 |
|------|---------|
| Release | `-O3 -DNDEBUG` |
| Debug | `-O0 -g3` |
| Alpha | `-O2 -g` |

需要支持 pthread 的 C11 编译器（gcc/clang）。平台矩阵见 [BUILD.md](BUILD.md)。

## 用法

### rev — 编译器

```bash
rev run <file.reo> [--target c|reo|c-freestanding]  # 编译并运行
rev build <file.reo> [-o out]                       # 编译为可执行文件 / 汇编
rev build <file.reo> --shared                       # 编译为共享库（.so/.dll）
rev build <file.reo> --target wasm                  # 编译为 WebAssembly (WASI)
rev build                                           # 构建项目（读取 ringecho.toml）
rev check <file.reo>                                # 仅类型检查
rev lsp                                             # 启动 LSP 服务器
rev venv <init|activate>                            # 管理虚拟环境
rev init [name]                                     # 创建新项目
rev clean                                           # 清理构建产物
```

`rev init` 会生成包含 `main.reo`、`ringecho.toml`、`.gitignore` 和 `.renv/` 虚拟环境的项目脚手架。不带参数的 `rev build` 从 `ringecho.toml` 读取入口并输出到 `target/Release/`。

### rem — 包管理器

```bash
rem init [name]        # 初始化新项目
rem install <pkg>      # 安装包
rem list               # 列出已安装的包
rem remove <pkg>       # 移除包
rem update             # 更新依赖
rem search <query>     # 搜索包
rem publish            # 发布当前包
```

### rvm — 版本管理器（独立项目）

`rvm` 已迁到 [RingAire/rvm](https://github.com/RingAire/rvm)：它从
`https://ringecho-lang.org/dist`（GitHub Releases 回退）安装已发布的编译器版本，
独立版本号、独立发布。

## 特性

- 完整类型系统（i8-i128、u8-u128、f32/f64、bool、char、str）
- 结构体、枚举、Trait + impl + 静态方法分派
- 泛型函数 + 结构体，惰性单态化
- Option/Result + `?` 运算符
- Lambda / 闭包（暂不支持捕获）
- Match 表达式（整数、浮点、布尔、字符、字符串内容匹配 + 枚举标签；保留标量结果类型）
- 管道运算符 `|>`
- Component 关键字
- 内核属性：静态变量/函数的 `@align`、`@no_mangle`/`@export_name`、`@noreturn`；`extern` 链接器变量
- for-in 区间 + 字符串迭代
- spawn/await 并发（pthread）
- GC：3 种模式（none/auto/manual）。`none` 不登记字符串；`manual` 提供
  `gc_retain`/`gc_release`（`gc_add_root`/`gc_remove_root` 同义）显式管理；
  `auto` 会在阈值处触发收集，但编译器自动插入 retain/release 尚未实现。
- LSP 服务器：JSON-RPC + 诊断
- 多文件模块（import 递归解析）
- extern C FFI
- char 类型，完整转义支持
- 虚拟环境（`.renv/`）及内置标准库（`std::io`、`std::math`、`std::string`、`std::vec`）
- 通过 `ringecho.toml` 进行项目配置

## 测试

`match` 的输入只求值一次，按顺序选择首个匹配分支，仅执行该分支。
模式必须能赋值给输入类型，各分支结果必须能赋值给首个分支的类型；
通配符 `_` 必须放在最后。建议始终提供 `_`：目前尚未做穷尽性检查，
无分支命中时数值结果为零，字符串结果为空字符串。

```reo
fn describe(value: str) -> str {
    return match value {
        "hello" => "greeting",
        _ => "other",
    };
}
```

运行带输出断言的 match 回归测试：`make CONFIG=Release test-match`（需要 Python 3）。

```bash
make CONFIG=Debug test          # 端到端：编译并运行全部正向测试，
                                # 校验预期失败（语义 / 语法 / 运行时）
make test-one FILE=tests/hello.reo   # 运行单个测试
make check-one FILE=tests/hello.reo  # 对单个测试做类型检查
make test-list                       # 列出全部测试
```

## 许可证

[Apache-2.0](LICENSE) - Copyright (c) 2025-2026 辉夜铃 (KaguyaRing) & Ringaire

## Star 趋势

<a href="https://www.star-history.com/#RingAire/ringecho-lang-c&amp;Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=RingAire/ringecho-lang-c&amp;type=Date&amp;theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=RingAire/ringecho-lang-c&amp;type=Date" />
    <img src="https://api.star-history.com/svg?repos=RingAire/ringecho-lang-c&amp;type=Date" alt="Star 趋势图" />
  </picture>
</a>
