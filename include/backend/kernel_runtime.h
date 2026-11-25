#ifndef RE0_KERNEL_RUNTIME_H
#define RE0_KERNEL_RUNTIME_H
#include "base/buffer.h"
/* Emits the freestanding hook ABI; requires stdint/stdbool/stddef first. */
void re0_kernel_hooks_emit(Re0Buffer *out);
#endif
