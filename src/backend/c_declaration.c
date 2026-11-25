#include "backend/c_declaration.h"
#include "backend/backend_c_internal.h"
#include "base/re0_limits.h"

void re0_c_declaration_attributes_emit(Re0Codegen *c, const Re0Stmt *stmt, bool definition) {
    if (!c || !stmt) return;
    bool used = definition && stmt->declaration.used;
    if (!stmt->declaration.section && !stmt->declaration.weak && !used) return;
    re0_buffer_write_str(&c->output, "__attribute__((");
    bool comma = false;
    if (stmt->declaration.section) {
        re0_buffer_write_str(&c->output, "section(");
        c_write_string_literal(&c->output, stmt->declaration.section);
        re0_buffer_write_char(&c->output, ')'); comma = true;
    }
    if (stmt->declaration.weak) {
        re0_buffer_write_str(&c->output, comma ? ", weak" : "weak"); comma = true;
    }
    if (used) re0_buffer_write_str(&c->output, comma ? ", used" : "used");
    re0_buffer_write_str(&c->output, ")) ");
}

static bool literal(const Re0Expr *e, unsigned depth) {
    if (!e || depth >= RE0_MAX_TYPE_DEPTH) return false;
    switch (e->kind) {
        case EXPR_INT: case EXPR_BOOL: case EXPR_CHAR: case EXPR_STRING: return true;
        case EXPR_ARRAY:
            if (e->array.count < 0 || (e->array.count && !e->array.elems)) return false;
            for (int i = 0; i < e->array.count; i++) if (!literal(e->array.elems[i], depth + 1)) return false;
            return true;
        case EXPR_STRUCT_INIT:
            if (e->struct_init.field_count < 0 || (e->struct_init.field_count && !e->struct_init.fields)) return false;
            for (int i = 0; i < e->struct_init.field_count; i++)
                if (!e->struct_init.fields[i].field || !literal(e->struct_init.fields[i].value, depth + 1)) return false;
            return true;
        default: return false;
    }
}

bool re0_c_static_literal(const Re0Expr *expression) { return literal(expression, 0); }

static void emit_literal(Re0Codegen *c, Re0Expr *e, unsigned depth) {
    if (!e || depth >= RE0_MAX_TYPE_DEPTH) { c_storage_fail("static literal nesting exceeds limit"); return; }
    if (e->kind == EXPR_ARRAY) {
        re0_buffer_write_str(&c->output, "{ .data = { ");
        for (int i = 0; i < e->array.count; i++) {
            if (i) re0_buffer_write_str(&c->output, ", ");
            emit_literal(c, e->array.elems[i], depth + 1);
        }
        re0_buffer_write_str(&c->output, " } }");
    } else if (e->kind == EXPR_STRUCT_INIT) {
        re0_buffer_write_str(&c->output, "{ ");
        for (int i = 0; i < e->struct_init.field_count; i++) {
            if (i) re0_buffer_write_str(&c->output, ", ");
            re0_buffer_write_fmt(&c->output, ".%s = ", e->struct_init.fields[i].field);
            emit_literal(c, e->struct_init.fields[i].value, depth + 1);
        }
        re0_buffer_write_str(&c->output, " }");
    } else c_gen_expr(c, e);
}

void re0_c_static_literal_emit(Re0Codegen *c, Re0Expr *expression) {
    if (!c || !expression) return;
    if (!re0_c_static_literal(expression)) { c_storage_fail("unsupported static literal initializer"); return; }
    emit_literal(c, expression, 0);
}
