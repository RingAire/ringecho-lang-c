# re0 自举：执行状态与验收门槛

## 目标与边界

最终目标是在 rnu / RingISA 用户态内运行 re0 编译器与构建工具，构建应用、
内核及编译器自身。现有 Windows/macOS/Linux 是引导宿主，不是语言的永久
平台边界。必须分别验收目标架构支持、目标操作系统运行库和原生构建宿主。

**当前只有由 C 参考编译器构建的 REO 前端种子，没有 Stage1/Stage2 完整
编译器，也没有 RingISA 后端或 rnu 原生构建能力。** 解析自己的词法器不等于
能构建自己；结构类型语法通过不等于布局、ABI 和代码生成全部实现。

## 2026-10-15 已执行的增量

- C 编译器的隐式整数扩宽和整数到浮点的精度判断统一采用目标布局。
  `re0_type_coercible_on` 是共享入口，旧 API 仅为宿主包装。
  Native lowering 与语义检查共用目标模型映射，不再分别假设宿主宽度。
- 空指针字面量必须 high/low 两部分同时为零，不能把 `2^64` 误认为 NULL。
- 自举前端分离共享存储、结构类型与声明模块。支持 i128/u128、isize/usize、
  逐层 const/mut/volatile 裸指针、引用、定长数组、切片、元组、函数类型、
  嵌套泛型参数的解析、规范打印及结构等价；支持 struct/union/别名声明 AST。
  这些表示不把宿主指针或宿主对象身份写入序列化节点。
- 修复 CRLF 自消费失败、作用域退出后名字泄漏及 else 块漏检查。
  反复分析前释放前次 token/AST/符号容器，释放临时收集列表。
- 新增源码 1 MiB、token 65536、诊断 128、类型递归 64 层及类型列表
  64 项上限；拒绝未闭合注释/字符串/字符和溢出数组长度。
  数组长度当前 AST 使用非负 i64，最大 `2^63-1`；这不是 RingISA 的
  完整 128 位 usize 常量支持，不应据此接受超过当前表示范围的对象。
- 修复空数组/零大小成员数组的 C 初始化；回归源码读取显式用 UTF-8。
  Windows hosted runtime 禁止 MinGW CRT 旧函数别名污染用户声明，保留
  winpthreads 的精确 pid_t 类型，目录判断使用 Windows `_stat64`。

## 已执行验证

```sh
make CONFIG=Release build
make CONFIG=Release test-type-qualifiers test-layout test-kernel-target
make CONFIG=Release test-selfhost test-selfhost-types PYTHON=python
make CONFIG=Release test test-native PYTHON=python
make CONFIG=Release test-ffi PYTHON=python
```

Windows 本地使用 `mingw32-make`、`SHELL="C:/PROGRA~1/Git/bin/sh.exe"`，
并将 TMP/TEMP 设为仓库已存在的 `target/rtmp`。

- 类型转换单测覆盖 32/64 位目标和**仅用于测试的**128 位指针布局；
  后者不是已安装 RingISA 目标。
- FFI 新增 4 个方法：五目标转换、赋值/字段/调用/static 拒绝、非零宽整数
  不能当空指针，以及六 native 目标下 12 次真实对象生成/拒绝。
- REO 前端原有四个种子自检通过；新增 Python 套件 5 个方法通过，含
  32 次生成类型往返、64 次恶意 token 模糊输入、非法限定符/长度/嵌套等。
  生成的完整前端另经 UBSan 编译执行，自检、递归超限和长度溢出路径无诊断。
- FFI 全量 66 个方法：60 执行通过，6 个原有平台相关跳过。
- Native 回归 63 个方法：22 执行通过，41 平台相关跳过。此前的 2 failures /
  1 error 已消除；不能将平台跳过计入目标机器执行证据。
- C 编译器本身构建无诊断。REO lint 与 hosted 生成 C 仍有既有警告；
  本轮不声称整个语言全部产物均已零警告。
- Native 单测及布局/类型存储分配失败注入通过（布局 8 点、类型存储 9 点）。
  同时修复这三个 make 入口在 Windows 下缺少可执行后缀及执行引用的问题。
- 独立 rnu 的 i686 QEMU 仍通过，退出 33；这不是 rnu 用户态自举验证。


## 2026-11-25 增量：前端语法自消费

- REO 前端新增 `--parse FILE`（只扫描/解析，不做名字解析）和 `--tokens FILE`。
- 补齐 `import`、顶层 `static`、`if` 表达式语法；修正 `at()` 只比较 token
  文本、导致字符串内容 `")"` 被当成右括号的问题（改为同时检查 token kind）。
- `compiler-reo/` 下 **全部 8 个 `.reo` 模块**都能被 REO 前端解析通过；
  `tests/selfhost/test_self_parse.py` 将其固定为回归。
- 这仍然只是语法自消费：`--file` 的 import 合并、static 符号、if 表达式类型
  检查尚未完成，Stage1 代码生成也没有开始。

## 后续门槛（尚未完成）

1. **完整前端自消费**：补 import/static/属性/初始化/所有表达式语法；前端能
   解析自身全部模块；建立真实类型符号、别名消解/循环拒绝、泛型替换、
   布局和完整语义检查，而非 TAny/TI64 占位推断。
2. **Stage1 可执行编译器**：REO 实现经验证的 IR、代码生成、错误传播与驱动；
   输入程序产生可运行对象/可执行文件，不能用 AST dump 冒充编译。
3. **Stage2 固定点**：Stage0 构建 Stage1，Stage1 构建 Stage2，Stage2 再构建；
   验证规范化产物/IR 一致性及完整正反例语料，记录可重现构建元数据。
4. **RingISA 目标**：正式数据/调用 ABI、128 位地址与指针运算、整数宽度策略、
   重定位/链接/装载及模拟器执行。现有 C 后端不提供不存在的 RingISA C 工具链。
5. **rnu 宿主**：用户隔离、系统调用、文件/内存/进程服务与运行库，再移植
   编译器和构建工具；在目标系统内部完成应用、内核和编译器重建。

## 审查范围与残余风险

本轮检查的信任边界为目标布局到隐式转换判断、整数到指针常量、输入类型
文本到有界 token/AST、列表/会话容器所有权和 Windows runtime 头文件边界。
测试仅在临时目录、宿主子进程和本地 QEMU 执行。

结构类型标识不提供活跃 union 成员分析、别名展开、借用/并发安全或 128 位
机器指针代码生成。表达式/语句解析仍是种子实现，不应作为不受限编译服务
暴露。Runtime 字符串及其他未改动子系统的资源管理不属于已完成的全仓审计。
MinGW 的旧 CRT 函数别名不再自动声明；外部 Windows CRT FFI 应显式采用
真实下划线 API 名称与签名。通用 C 符号/保留字转义仍需独立实现。
