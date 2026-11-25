#include "front/declaration_attributes.h"
#include "base/re0_limits.h"
#include <string.h>

static bool reject(Re0ErrorList *errors, Re0Span span, const char *message) {
    re0_error_append(errors, RE0_ERR_SYNTAX, span, NULL, "%s", message);
    return false;
}

bool re0_declaration_attribute_apply(Re0ErrorList *errors, Re0Span span,
    const char *name, const char *argument, bool string_argument,
    bool parentheses, Re0Stmt *inner) {
    if (!name) return reject(errors, span, "missing declaration attribute name");
    bool section = strcmp(name, "section") == 0;
    bool used = strcmp(name, "used") == 0;
    bool weak = strcmp(name, "weak") == 0;
    if (!section && !used && !weak) return true;
    unsigned depth = 0;
    while (inner && (inner->kind == STMT_ATTRIBUTE || inner->kind == STMT_PUB)) {
        if (++depth > RE0_MAX_PARSE_DEPTH) return reject(errors, span, "declaration attribute nesting exceeds limit");
        inner = inner->kind == STMT_ATTRIBUTE ? inner->attribute.inner : inner->pub.inner;
    }
    if (!inner || (inner->kind != STMT_FUNCTION && inner->kind != STMT_STATIC))
        return reject(errors, span, "section/used/weak require a function or static object definition");
    if (inner->kind == STMT_FUNCTION && (inner->function.type_param_count || inner->function.is_async))
        return reject(errors, span, "declaration attributes on generic/async functions are not supported");
    if (weak && inner->kind != STMT_FUNCTION)
        return reject(errors, span, "@weak requires a function with external linkage");
    if (section) {
        if (!string_argument || !argument || !*argument)
            return reject(errors, span, "@section requires a nonempty string argument");
        size_t n = strnlen(argument, RE0_MAX_SECTION_NAME + 1);
        if (n > RE0_MAX_SECTION_NAME) return reject(errors, span, "section name exceeds 127 bytes");
        for (size_t i = 0; i < n; i++) {
            unsigned char c = (unsigned char)argument[i];
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '$' || c == '-'))
                return reject(errors, span, "invalid character in section name");
        }
        if (inner->declaration.section) return reject(errors, span, "duplicate @section attribute");
        inner->declaration.section = argument;
    } else {
        if (parentheses || argument) return reject(errors, span, "@used and @weak do not accept arguments or parentheses");
        bool *flag = used ? &inner->declaration.used : &inner->declaration.weak;
        if (*flag) return reject(errors, span, "duplicate declaration attribute");
        *flag = true;
    }
    return true;
}
