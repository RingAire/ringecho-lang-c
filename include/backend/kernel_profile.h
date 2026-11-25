#ifndef RE0_KERNEL_PROFILE_H
#define RE0_KERNEL_PROFILE_H
#include "base/buffer.h"

/* Kernel profile code generation (C backend).
 *
 * A kernel-profile program is compiled for a bare-metal target with no host C
 * library; it is linked by a linker script against an external startup (see
 * exec/kernel_build.h). This module owns the C text that the kernel profile
 * injects in front of the generated program:
 *
 *   re0_kernel_prelude_emit  — the self-contained prelude: freestanding header
 *                              set, weak kernel hooks, and libc stand-ins so
 *                              the generated C needs nothing from the host.
 *   re0_kernel_runtime_emit  — the minimal runtime helpers referenced by
 *                              kernel-profile code generation (optional
 *                              128-bit integer support; no hosted conversion
 *                              runtime).
 *
 * Keeping this text in a dedicated module avoids embedding large C program
 * fragments inside backend_c.c / runtime_conversion.c. */
void re0_kernel_prelude_emit(Re0Buffer *out);
void re0_kernel_runtime_emit(Re0Buffer *out);

#endif
