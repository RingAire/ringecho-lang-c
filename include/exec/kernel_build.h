#ifndef RE0_KERNEL_BUILD_H
#define RE0_KERNEL_BUILD_H
#include "base/error.h"
#include "base/target.h"
#include <stdbool.h>

#define RE0_KERNEL_MAX_INPUTS 16

/* Forward declaration; Re0Build is defined in exec/build.h. This header does
 * not include build.h so the two remain acyclic. */
typedef struct Re0Build Re0Build;

/* Kernel-profile build configuration and inputs.
 *
 * A kernel build is a two-step freestanding build for a bare-metal target:
 * the generated C and any assembly inputs are compiled to objects with a cross
 * compiler, then linked with the ELF linker (default `ld.lld`) against an
 * optional linker script. The C backend emits the matching self-contained
 * prelude/runtime (see backend/kernel_profile.h). */
typedef struct {
    bool         enabled;
    bool         emit_object;    /* only the generated module, without linking */
    const char  *cc;             /* NULL -> REO_KERNEL_CC, else built-in default */
    const char  *target;         /* NULL -> REO_KERNEL_TARGET, else built-in default */
    const char  *linker_script;  /* optional `-T` linker script */
    const char  *asm_files[RE0_KERNEL_MAX_INPUTS];
    int          asm_count;
    const char  *object_files[RE0_KERNEL_MAX_INPUTS];
    int          object_count;
} Re0KernelBuild;

void re0_kernel_build_init(Re0KernelBuild *k);
/* Reject empty/response-file paths or invalid/full input counts. Object paths
 * beginning with '-' must use './' or an absolute path (lld has no '--'). Paths
 * are passed as argv operands, not shell commands or compiler options. */
bool re0_kernel_build_add_asm(Re0KernelBuild *k, const char *path);
bool re0_kernel_build_add_object(Re0KernelBuild *k, const char *path);
void re0_kernel_build_set_linker_script(Re0KernelBuild *k, const char *path);

/* Resolve config/environment/default identically for semantics and code build.
 * layout returns NULL for triples without a verified machine model. */
const char *re0_kernel_build_target(const Re0KernelBuild *k);
const Re0TargetLayout *re0_kernel_build_layout(const Re0KernelBuild *k);

/* Write `c_code` to the build's private temp file, compile it and the
 * configured assembly inputs to objects, then link a bare-metal image into
 * `output_path`. Temporary C/assembly objects are removed on every exit unless
 * keep_c is enabled (the existing default; REO_KEEP_C=0 enables cleanup).
 * REO_KERNEL_OPT accepts -O0/-O1/-O2/-O3/-Os/-Oz; other values warn and use -O2. */
/* REO_KERNEL_REGISTER_POLICY defaults to general: no implicit FP/SIMD register
 * use. full restores toolchain defaults; the platform must enable and save the
 * corresponding CPU state. Invalid values warn and fall back to general. */
bool re0_kernel_build_run(Re0Build *b, const char *c_code, const char *output_path);

#endif
