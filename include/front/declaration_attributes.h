#ifndef RE0_DECLARATION_ATTRIBUTES_H
#define RE0_DECLARATION_ATTRIBUTES_H
#include "front/ast.h"
#include "base/error.h"
enum { RE0_MAX_SECTION_NAME = 127 };
/* Recognized attribute strings are borrowed from the parser arena. */
bool re0_declaration_attribute_apply(Re0ErrorList *errors, Re0Span span,
    const char *name, const char *argument, bool string_argument,
    bool parentheses, Re0Stmt *inner);
#endif
