#ifndef RE0_KERNEL_ARITHMETIC_H
#define RE0_KERNEL_ARITHMETIC_H
#include "backend/codegen.h"

/* Freestanding, width-aware integer operations. The generated helpers require
 * the kernel profile's _Noreturn __reo_kernel_fail definition. */
void re0_kernel_arithmetic_emit(Re0Buffer *out);
void re0_kernel_binary_emit(Re0Codegen *c, Re0Expr *expression);
void re0_kernel_negate_emit(Re0Codegen *c, Re0Expr *expression);
void re0_kernel_integer_cast_emit(Re0Codegen *c, Re0Expr *expression);

#endif
