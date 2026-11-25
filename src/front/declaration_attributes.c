#include "front/declaration_attributes.h"
#include "base/re0_limits.h"
#include <string.h>

static bool reject(Re0ErrorList *errors, Re0Span span, const char *message) {
    re0_error_append(errors, RE0_ERR_SYNTAX, span, NULL, "%s", message);
    return false;
}

static bool valid_export_name(const char *name) {
    if (!name || !*name) return false;
    if (!((name[0] >= 'a' && name[0] <= 'z') || (name[0] >= 'A' && name[0] <= 'Z') || name[0] == '_'))
        return false;
    for (const char *p = name + 1; *p; ++p) {
        if (!((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
              (*p >= '0' && *p <= '9') || *p == '_'))
            return false;
    }
    return true;
}

bool re0_declaration_attribute_apply(Re0ErrorList *errors, Re0Span span,
    const char *name, const char *argument, bool string_argument,
    bool parentheses, Re0Stmt *inner) {
    if (!name) return reject(errors, span, "missing declaration attribute name");

    unsigned depth = 0;
    Re0Stmt *target = inner;
    while (target && (target->kind == STMT_ATTRIBUTE || target->kind == STMT_PUB)) {
        if (++depth > RE0_MAX_PARSE_DEPTH) return reject(errors, span, "declaration attribute nesting exceeds limit");
        target = target->kind == STMT_ATTRIBUTE ? target->attribute.inner : target->pub.inner;
    }

    bool is_function = target && target->kind == STMT_FUNCTION;

    if (strcmp(name, "section") == 0 || strcmp(name, "used") == 0 || strcmp(name, "weak") == 0) {
        bool section = strcmp(name, "section") == 0;
        bool used = strcmp(name, "used") == 0;
        bool weak = strcmp(name, "weak") == 0;
        if (!target || (target->kind != STMT_FUNCTION && target->kind != STMT_STATIC))
            return reject(errors, span, "section/used/weak require a function or static object definition");
        if (is_function && (target->function.type_param_count || target->function.is_async))
            return reject(errors, span, "declaration attributes on generic/async functions are not supported");
        if (weak && !is_function)
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
            if (target->declaration.section) return reject(errors, span, "duplicate @section attribute");
            target->declaration.section = argument;
        } else {
            if (parentheses || argument) return reject(errors, span, "@used and @weak do not accept arguments or parentheses");
            bool *flag = used ? &target->declaration.used : &target->declaration.weak;
            if (*flag) return reject(errors, span, "duplicate declaration attribute");
            *flag = true;
        }
        return true;
    }

    if (strcmp(name, "align") == 0 || strcmp(name, "repr") == 0) {
        /* Value and target validation happens in apply_layout_attribute. */
        return true;
    }

    if (strcmp(name, "cfg") == 0) {
        if (!argument || !*argument) return reject(errors, span, "@cfg requires a condition");
        if (strcmp(argument, "windows") != 0 && strcmp(argument, "macos") != 0 &&
            strcmp(argument, "linux") != 0)
            return reject(errors, span, "unsupported @cfg condition (expected windows, macos or linux)");
        return true;
    }

    if (strcmp(name, "gc") == 0) {
        if (!argument || !*argument) return reject(errors, span, "@gc requires none, auto or manual");
        if (strcmp(argument, "none") != 0 && strcmp(argument, "auto") != 0 &&
            strcmp(argument, "manual") != 0)
            return reject(errors, span, "@gc expects none, auto or manual");
        return true;
    }

    if (strcmp(name, "no_mangle") == 0 || strcmp(name, "export_name") == 0 ||
        strcmp(name, "noreturn") == 0) {
        if (!is_function)
            return reject(errors, span, "no_mangle/export_name/noreturn require a function definition");
        if (target->function.type_param_count || target->function.is_async)
            return reject(errors, span, "no_mangle/export_name/noreturn are not supported on generic/async functions");
        if (strcmp(target->function.name, "main") == 0)
            return reject(errors, span, "the entry function 'main' cannot be renamed or marked noreturn");
        if (strcmp(name, "no_mangle") == 0) {
            if (parentheses || argument) return reject(errors, span, "@no_mangle does not accept arguments");
            if (target->declaration.export_name) return reject(errors, span, "duplicate export name attribute");
            target->declaration.no_mangle = true;
            target->declaration.export_name = target->function.name;
            return true;
        }
        if (strcmp(name, "export_name") == 0) {
            if (!string_argument || !argument || !*argument)
                return reject(errors, span, "@export_name requires a nonempty string argument");
            if (strnlen(argument, 128) >= 128) return reject(errors, span, "export name exceeds 127 bytes");
            if (!valid_export_name(argument))
                return reject(errors, span, "@export_name must be a valid C identifier");
            if (target->declaration.export_name) return reject(errors, span, "duplicate export name attribute");
            target->declaration.export_name = argument;
            return true;
        }
        if (parentheses || argument) return reject(errors, span, "@noreturn does not accept arguments");
        if (target->declaration.noreturn) return reject(errors, span, "duplicate @noreturn attribute");
        target->declaration.noreturn = true;
        return true;
    }

    re0_error_append(errors, RE0_ERR_SYNTAX, span, NULL,
                     "unknown declaration attribute '@%s'", name);
    return false;
}
