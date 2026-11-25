#include "exec/kernel_build.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    const struct { const char *triple; const Re0TargetLayout *layout; } cases[] = {
        {"i686-unknown-none-elf", &re0_target_x86_sysv},
        {"i386-unknown-none-elf", &re0_target_x86_sysv},
        {"x86_64-unknown-none-elf", &re0_target_x86_64_sysv},
        {"aarch64-unknown-none-elf", &re0_target_aarch64_lp64},
        {"armv7-unknown-none-eabi", &re0_target_arm_aapcs},
        {"aarch64_be-unknown-none-elf", NULL},
        {"x86_64-pc-windows-msvc", NULL},
        {"riscv64-unknown-none-elf", NULL},
        {"unknown-x86_64", NULL}
    };
    Re0KernelBuild k; re0_kernel_build_init(&k);
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        k.target = cases[i].triple;
        if (strcmp(re0_kernel_build_target(&k), k.target) != 0 ||
            re0_kernel_build_layout(&k) != cases[i].layout) {
            fprintf(stderr, "kernel target model mismatch: %s\n", k.target); return 1;
        }
    }
    if (re0_kernel_build_target(NULL) || re0_kernel_build_layout(NULL)) return 1;
    re0_kernel_build_init(&k);
    if (re0_kernel_build_add_asm(&k, "") || re0_kernel_build_add_asm(&k, "@options") ||
        re0_kernel_build_add_object(&k, "-Tscript") || re0_kernel_build_add_object(&k, "@options")) return 1;
    k.asm_count = -1; k.object_count = -1;
    if (re0_kernel_build_add_asm(&k, "test.S") || re0_kernel_build_add_object(&k, "test.o")) return 1;
    re0_kernel_build_init(&k);
    for (int i = 0; i < RE0_KERNEL_MAX_INPUTS; ++i)
        if (!re0_kernel_build_add_asm(&k, "test.S") || !re0_kernel_build_add_object(&k, "test.o")) return 1;
    if (re0_kernel_build_add_asm(&k, "test.S") || re0_kernel_build_add_object(&k, "test.o")) return 1;
    puts("kernel target models and unsupported-target rejection passed");
    return 0;
}
