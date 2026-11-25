#ifndef RE0_C_DECLARATION_H
#define RE0_C_DECLARATION_H
#include "backend/codegen.h"
void re0_c_declaration_attributes_emit(Re0Codegen *c, const Re0Stmt *stmt, bool definition);
bool re0_c_static_literal(const Re0Expr *expression);
void re0_c_static_literal_emit(Re0Codegen *c, Re0Expr *expression);
#endif
