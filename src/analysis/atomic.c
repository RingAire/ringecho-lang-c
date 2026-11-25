#include "analysis/atomic.h"
#include <string.h>

bool re0_atomic_name(const char *name) {
    if (!name) return false;
    const char *names[] = {"atomic_load", "atomic_store", "atomic_exchange", "atomic_compare_exchange",
        "atomic_fetch_add", "atomic_fetch_sub", "atomic_fetch_and", "atomic_fetch_or", "atomic_fetch_xor", "atomic_fence"};
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i)
        if (strcmp(name, names[i]) == 0) return true;
    return false;
}

int re0_atomic_order(const Re0Expr *e) {
    if (!e || e->kind != EXPR_STRING || !e->str_lit.val) return -1;
    const char *names[] = {"relaxed", "acquire", "release", "acq_rel", "seq_cst"};
    for (int i = 0; i < 5; ++i) if (strcmp(e->str_lit.val, names[i]) == 0) return i;
    return -1;
}

static void error(Re0Sema *s, Re0Expr *e, const char *message) {
    re0_error_append(s->errors, RE0_ERR_SEMANTIC, e->span, NULL, "atomic operation: %s", message);
    s->had_error = true;
}

static Re0Type *pointee(Re0Sema *s, Re0Expr *call, Re0Expr *arg, bool mutable) {
    Re0Type *t = arg ? arg->resolved_type : NULL;
    if (!t || t->kind != RE0_TYPE_PTR || !t->ptr_.inner || (mutable && !t->ptr_.mutable_)) {
        error(s, call, mutable ? "requires a typed mutable raw pointer" : "requires a typed raw pointer");
        return NULL;
    }
    Re0Type *inner = t->ptr_.inner;
    if (!(re0_type_is_integer(inner->kind) || inner->kind == RE0_TYPE_BOOL || inner->kind == RE0_TYPE_PTR) ||
        re0_type_sizeof_on(s->target, inner->kind) > s->target->pointer_size) {
        error(s, call, "type is not supported as a naturally aligned lock-free atomic on this target");
        return NULL;
    }
    return inner;
}

Re0Type *re0_atomic_check(Re0Sema *s, Re0Expr *e) {
    if (!s || !e || e->kind != EXPR_CALL || !e->call.callee || e->call.callee->kind != EXPR_IDENT)
        return NULL;
    const char *name = e->call.callee->ident.name;
    if (!re0_atomic_name(name)) return NULL;
    bool load = strcmp(name, "atomic_load") == 0;
    bool store = strcmp(name, "atomic_store") == 0;
    bool fence = strcmp(name, "atomic_fence") == 0;
    bool compare = strcmp(name, "atomic_compare_exchange") == 0;
    bool fetch = strncmp(name, "atomic_fetch_", 13) == 0;
    int count = fence ? 1 : compare ? 5 : load ? 2 : 3;
    if (e->call.arg_count != count || !e->call.args || !s->target) {
        error(s, e, "incorrect number of arguments");
        return re0_type_make(RE0_TYPE_UNKNOWN, NULL);
    }
    for (int i = 0; i < count; ++i) {
        if (!e->call.args[i]) {
            error(s, e, "missing argument expression");
            return re0_type_make(RE0_TYPE_UNKNOWN, NULL);
        }
    }
    int success = re0_atomic_order(e->call.args[count - (compare ? 2 : 1)]);
    if (success < 0 || (load && (success == 2 || success == 3)) ||
        (store && (success == 1 || success == 3)) || (fence && success == 0))
        error(s, e, "invalid memory order for this operation (must be a supported string literal)");
    if (compare) {
        int failure = re0_atomic_order(e->call.args[4]);
        /* Failure may not release or be stronger than success. */
        bool allowed = failure == 0 || (failure == 1 && (success == 1 || success == 3 || success == 4)) ||
                       (failure == 4 && success == 4);
        if (success < 0 || !allowed) error(s, e, "invalid compare-exchange failure memory order");
    }
    if (fence) return re0_type_make(RE0_TYPE_UNIT, NULL);
    Re0Type *type = pointee(s, e, e->call.args[0], !load);
    if (!type) return re0_type_make(RE0_TYPE_UNKNOWN, NULL);
    if (fetch && !re0_type_is_integer(type->kind)) error(s, e, "fetch operations require an integer pointee");
    if (!load) {
        Re0Expr *value = e->call.args[compare ? 2 : 1];
        if (!value || !re0_type_equal(value->resolved_type, type))
            error(s, e, "value must have exactly the pointee type; use a typed literal or explicit cast");
    }
    if (compare) {
        Re0Type *expected = pointee(s, e, e->call.args[1], true);
        if (e->call.args[1]->resolved_type && e->call.args[1]->resolved_type->is_volatile)
            error(s, e, "expected storage must be ordinary thread-local memory, not volatile");
        if (!expected || !re0_type_equal(expected, type)) error(s, e, "expected pointer must have the same pointee type");
    }
    return store ? re0_type_make(RE0_TYPE_UNIT, NULL) : compare ? re0_type_make(RE0_TYPE_BOOL, NULL) : type;
}
