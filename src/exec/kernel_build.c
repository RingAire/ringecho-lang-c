#include "exec/kernel_build.h"
#include "exec/build.h"
#include "exec/process.h"
#include "platform.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>

/* ── Kernel-profile build defaults ────────────────────────────────────────
 * Centralized here so backend/CLI code does not embed literals. Each has an
 * environment override for non-default toolchains. */
#define RE0_KERNEL_ENV_CC     "REO_KERNEL_CC"
#define RE0_KERNEL_ENV_TARGET "REO_KERNEL_TARGET"
#define RE0_KERNEL_ENV_OPT    "REO_KERNEL_OPT"
#define RE0_KERNEL_ENV_LD     "REO_KERNEL_LD"
#define RE0_KERNEL_ENV_REGISTERS "REO_KERNEL_REGISTER_POLICY"

static const char KERNEL_DEFAULT_CC[]     = "clang";
static const char KERNEL_DEFAULT_TARGET[] = "i686-unknown-none-elf";
static const char KERNEL_DEFAULT_OPT[]    = "-O2";
static const char KERNEL_DEFAULT_REGISTERS[] = "general";
#if defined(RE0_PLATFORM_WINDOWS)
/* CreateProcessA only appends `.exe` when the name has no extension, so the
 * ELF linker must be named explicitly on Windows. */
static const char KERNEL_DEFAULT_LD[]     = "ld.lld.exe";
#else
static const char KERNEL_DEFAULT_LD[]     = "ld.lld";
#endif

/* Resolve a value from (config -> environment -> built-in default). */
static const char *kernel_pick(const char *configured, const char *env_name,
                               const char *fallback) {
    if (configured && *configured) return configured;
    const char *env = getenv(env_name);
    if (env && *env) return env;
    return fallback;
}

void re0_kernel_build_init(Re0KernelBuild *k) {
    if (!k) return;
    memset(k, 0, sizeof(*k));
    k->enabled = false;
}

const char *re0_kernel_build_target(const Re0KernelBuild *k) {
    return k ? kernel_pick(k->target, RE0_KERNEL_ENV_TARGET, KERNEL_DEFAULT_TARGET) : NULL;
}

const Re0TargetLayout *re0_kernel_build_layout(const Re0KernelBuild *k) {
    const char *target = re0_kernel_build_target(k);
    if (!target) return NULL;
    if (strcmp(target, "i686-unknown-none-elf") == 0 || strcmp(target, "i386-unknown-none-elf") == 0)
        return &re0_target_x86_sysv;
    if (strcmp(target, "x86_64-unknown-none-elf") == 0)
        return &re0_target_x86_64_sysv;
    if (strcmp(target, "aarch64-unknown-none-elf") == 0)
        return &re0_target_aarch64_lp64;
    if (strcmp(target, "armv7-unknown-none-eabi") == 0)
        return &re0_target_arm_aapcs;
    return NULL;
}

bool re0_kernel_build_add_asm(Re0KernelBuild *k, const char *path) {
    if (!k || !path || !*path || *path == '@' || k->asm_count < 0 || k->asm_count >= RE0_KERNEL_MAX_INPUTS) return false;
    k->asm_files[k->asm_count++] = path;
    return true;
}

bool re0_kernel_build_add_object(Re0KernelBuild *k, const char *path) {
    if (!k || !path || !*path || *path == '@' || *path == '-' || k->object_count < 0 || k->object_count >= RE0_KERNEL_MAX_INPUTS) return false;
    k->object_files[k->object_count++] = path;
    return true;
}

void re0_kernel_build_set_linker_script(Re0KernelBuild *k, const char *path) {
    if (k) k->linker_script = path;
}

/* Append the shared kernel-profile compile flags (freestanding, no host runtime). */
static int kernel_compile_flags(const char *cc, const char *target, const char *opt,
                                bool no_red_zone, bool general_registers, const char **args, int n) {
    args[n++] = cc;
    args[n++] = "-target";
    args[n++] = target;
    args[n++] = opt;
    args[n++] = "-ffreestanding";
    args[n++] = "-fno-builtin";
    args[n++] = "-fno-stack-protector";
    args[n++] = "-fno-pic";
    if (no_red_zone) args[n++] = "-mno-red-zone";
    if (general_registers) {
        if (!strcmp(target, "armv7-unknown-none-eabi")) {
            args[n++] = "-mfloat-abi=soft";
            args[n++] = "-mfpu=none";
        } else args[n++] = "-mgeneral-regs-only";
    }
    args[n++] = "-Wno-unused-value";
    args[n++] = "-Wno-unused-variable";
    args[n++] = "-Wno-unused-function";
    args[n++] = "-ffunction-sections";
    args[n++] = "-fdata-sections";
    return n;
}

/* Compile a single C/asm source into `object_path`. */
static bool kernel_compile_one(const char *cc, const char *target, const char *opt,
                               bool no_red_zone, bool general_registers, const char *src, const char *object_path) {
    const char *args[64];
    int n = kernel_compile_flags(cc, target, opt, no_red_zone, general_registers, args, 0);
    args[n++] = "-c";
    args[n++] = "-o";
    args[n++] = object_path;
    args[n++] = "--";
    args[n++] = src;
    args[n] = NULL;
    return re0_process_run(cc, args) == 0;
}

/* Map a target triple to an ELF linker emulation (NULL = let lld infer). */
static const char *kernel_ld_emulation(const char *target) {
    if (strstr(target, "x86_64")) return "elf_x86_64";
    if (strstr(target, "i686") || strstr(target, "i386")) return "elf_i386";
    if (strstr(target, "aarch64")) return "aarch64elf";
    if (strstr(target, "arm")) return "armelf";
    return NULL;
}

bool re0_kernel_build_run(Re0Build *b, const char *c_code, const char *output_path) {
    if (!b || !c_code || !output_path || !*output_path) return false;
    Re0KernelBuild *k = &b->kernel;
    if (k->emit_object && (k->asm_count || k->object_count || k->linker_script)) {
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                         "kernel --emit obj compiles one REO module; assembly/object/linker-script inputs belong to the final link");
        return false;
    }
    if (k->asm_count < 0 || k->asm_count > RE0_KERNEL_MAX_INPUTS ||
        k->object_count < 0 || k->object_count > RE0_KERNEL_MAX_INPUTS) {
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL, "invalid kernel input count");
        return false;
    }
    for (int i = 0; i < k->asm_count; ++i) {
        if (!k->asm_files[i] || !*k->asm_files[i] || *k->asm_files[i] == '@') {
            re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL, "invalid kernel assembly input (response files are not allowed)"); return false;
        }
    }
    for (int i = 0; i < k->object_count; ++i) {
        if (!k->object_files[i] || !*k->object_files[i] || *k->object_files[i] == '@' || *k->object_files[i] == '-') {
            re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL, "invalid kernel object input (use ./ for filenames beginning with - or @)"); return false;
        }
    }
    if (!re0_kernel_build_layout(k)) {
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                         "unsupported kernel target layout: %s", re0_kernel_build_target(k));
        return false;
    }
    if (!re0_build_write_source(b, c_code)) return false;
    if (b->tmp_file[0] == '-' || b->tmp_file[0] == '@') {
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                         "kernel temporary directory must not produce option-like relative paths; use an absolute TMP directory");
        return false;
    }

    const char *cc = kernel_pick(k->cc, RE0_KERNEL_ENV_CC, KERNEL_DEFAULT_CC);
    const char *target = re0_kernel_build_target(k);
    const char *opt = kernel_pick(NULL, RE0_KERNEL_ENV_OPT, KERNEL_DEFAULT_OPT);
    if (strcmp(opt, "-O0") && strcmp(opt, "-O1") && strcmp(opt, "-O2") && strcmp(opt, "-O3") &&
        strcmp(opt, "-Os") && strcmp(opt, "-Oz")) {
        re0_error_append(b->errors, RE0_WARN, RE0_SPAN_ZERO, NULL,
                         "invalid REO_KERNEL_OPT; using default -O2");
        opt = KERNEL_DEFAULT_OPT;
    }
    const char *ld = kernel_pick(NULL, RE0_KERNEL_ENV_LD, KERNEL_DEFAULT_LD);
    const char *register_policy = kernel_pick(NULL, RE0_KERNEL_ENV_REGISTERS, KERNEL_DEFAULT_REGISTERS);
    if (strcmp(register_policy, "general") && strcmp(register_policy, "full")) {
        re0_error_append(b->errors, RE0_WARN, RE0_SPAN_ZERO, NULL,
                         "invalid REO_KERNEL_REGISTER_POLICY; using default general");
        register_policy = KERNEL_DEFAULT_REGISTERS;
    }
    bool general_registers = !strcmp(register_policy, "general");
    const bool no_red_zone = strstr(target, "x86_64") != NULL;

    /* Object output paths live next to the generated C in the private temp dir. */
    char c_obj[600] = {0};
    char asm_obj[RE0_KERNEL_MAX_INPUTS][600];
    int asm_paths = 0;
    bool ok = false;
    int length = snprintf(c_obj, sizeof(c_obj), "%s.o", b->tmp_file);
    if (length < 0 || length >= (int)sizeof(c_obj)) {
        c_obj[0] = '\0';
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                         "temporary object path is too long");
        goto cleanup;
    }

    /* Step 1: compile the generated C to an object. clang's MinGW driver links
     * through the host toolchain for this target, so linking is done separately. */
    if (!kernel_compile_one(cc, target, opt, no_red_zone, general_registers, b->tmp_file, k->emit_object ? output_path : c_obj)) {
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                         "kernel compilation of generated C failed");
        goto cleanup;
    }
    if (k->emit_object) { ok = true; goto cleanup; }
    /* Step 2: assemble each extra assembly source. */
    for (int i = 0; i < k->asm_count; i++) {
        length = snprintf(asm_obj[i], sizeof(asm_obj[i]), "%s.%d.o", b->tmp_file, i);
        if (length < 0 || length >= (int)sizeof(asm_obj[i])) {
            re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                             "temporary object path is too long");
            goto cleanup;
        }
        ++asm_paths;
        if (!kernel_compile_one(cc, target, opt, no_red_zone, general_registers, k->asm_files[i], asm_obj[i])) {
            re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                             "kernel assembly of '%s' failed", k->asm_files[i]);
            goto cleanup;
        }
    }

    /* Step 3: link the objects with the ELF linker. */
    const char *args[256];
    int n = 0;
    args[n++] = ld;
    args[n++] = "--gc-sections";
    args[n++] = "--build-id=none";
    args[n++] = "-static";
    const char *emu = kernel_ld_emulation(target);
    if (emu) { args[n++] = "-m"; args[n++] = emu; }
    if (k->linker_script && *k->linker_script) {
        args[n++] = "-T";
        args[n++] = k->linker_script;
    }
    args[n++] = "-o";
    args[n++] = output_path;
    args[n++] = c_obj;
    for (int i = 0; i < k->asm_count; i++) args[n++] = asm_obj[i];
    for (int i = 0; i < k->object_count; i++) args[n++] = k->object_files[i];
    args[n] = NULL;

    int rc = re0_process_run(ld, args);
    if (rc != 0) {
        re0_error_append(b->errors, RE0_ERR_IO, RE0_SPAN_ZERO, NULL,
                         "kernel linking failed (exit code %d)", rc);
        goto cleanup;
    }
    ok = true;
cleanup:
    if (!b->keep_c) {
        for (int i = 0; i < asm_paths; i++) {
            if (remove(asm_obj[i]) != 0 && errno != ENOENT)
                re0_error_append(b->errors, RE0_WARN, RE0_SPAN_ZERO, NULL, "cannot remove temporary assembly object '%s'", asm_obj[i]);
        }
        if (*c_obj && remove(c_obj) != 0 && errno != ENOENT)
            re0_error_append(b->errors, RE0_WARN, RE0_SPAN_ZERO, NULL, "cannot remove temporary C object '%s'", c_obj);
        if (remove(b->tmp_file) != 0 && errno != ENOENT) {
            re0_error_append(b->errors, RE0_WARN, RE0_SPAN_ZERO, NULL,
                             "cannot remove temporary C file '%s'", b->tmp_file);
        }
    }
    return ok;
}
