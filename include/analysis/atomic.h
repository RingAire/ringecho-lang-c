#ifndef RE0_ANALYSIS_ATOMIC_H
#define RE0_ANALYSIS_ATOMIC_H
#include "analysis/sema.h"
bool re0_atomic_name(const char *name);
/* Arguments must already have resolved types. Result is sema-owned. */
Re0Type *re0_atomic_check(Re0Sema *sema, Re0Expr *call);
int re0_atomic_order(const Re0Expr *expression);
#endif
