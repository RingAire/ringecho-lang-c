#include "backend/c_atomic.h"
#include "backend/backend_c_internal.h"
#include "analysis/atomic.h"

static const char *order(Re0Expr *e) {
    static const char *names[] = {"__ATOMIC_RELAXED", "__ATOMIC_ACQUIRE", "__ATOMIC_RELEASE", "__ATOMIC_ACQ_REL", "__ATOMIC_SEQ_CST"};
    int value = re0_atomic_order(e);
    return value < 0 ? NULL : names[value];
}

void re0_c_atomic_emit(Re0Codegen *c, Re0Expr *e) {
    if (!c || !e || e->kind != EXPR_CALL || !e->call.callee || e->call.callee->kind != EXPR_IDENT) return;
    const char *name = e->call.callee->ident.name;
    bool fence = strcmp(name, "atomic_fence") == 0;
    bool load = strcmp(name, "atomic_load") == 0;
    bool store = strcmp(name, "atomic_store") == 0;
    bool compare = strcmp(name, "atomic_compare_exchange") == 0;
    int count = fence ? 1 : compare ? 5 : load ? 2 : 3;
    if (!re0_atomic_name(name) || e->call.arg_count != count || !e->call.args || !order(e->call.args[count - (compare ? 2 : 1)]) ||
        (compare && !order(e->call.args[4]))) {
        re0_error_append(c->errors, RE0_ERR_SEMANTIC, e->span, NULL, "invalid atomic lowering input");
        c->had_error = true; return;
    }
    for (int i = 0; i < count; ++i) {
        if (!e->call.args[i]) {
            re0_error_append(c->errors, RE0_ERR_SEMANTIC, e->span, NULL, "missing atomic lowering argument");
            c->had_error = true; return;
        }
    }
    Re0Buffer *out = &c->output;
    if (fence) {
        re0_buffer_write_fmt(out, "__atomic_thread_fence(%s)", order(e->call.args[0])); return;
    }
    int id = c->temp_counter++;
    re0_buffer_write_fmt(out, "({ __auto_type __atomic_p%d = (", id);
    c_gen_expr(c, e->call.args[0]);
    re0_buffer_write_fmt(out, "); if (!__atomic_p%d || (uintptr_t)__atomic_p%d %% sizeof(*__atomic_p%d)) __reo_null_call(); ", id, id, id);
    re0_buffer_write_fmt(out, "_Static_assert(__atomic_always_lock_free(sizeof(*__atomic_p%d), 0), \"atomic operation must be lock-free\"); ", id);
    if (compare) {
        re0_buffer_write_fmt(out, "__auto_type __atomic_expected%d = (", id);
        c_gen_expr(c, e->call.args[1]);
        re0_buffer_write_fmt(out, "); if (!__atomic_expected%d || (uintptr_t)__atomic_expected%d %% sizeof(*__atomic_expected%d) || (uintptr_t)__atomic_expected%d == (uintptr_t)__atomic_p%d) __reo_null_call(); ", id, id, id, id, id);
    }
    if (!load) {
        re0_buffer_write_fmt(out, "__auto_type __atomic_value%d = (", id);
        c_gen_expr(c, e->call.args[compare ? 2 : 1]);
        re0_buffer_write_str(out, "); ");
    }
    const char *builtin = load ? "__atomic_load_n" : store ? "__atomic_store_n" : compare ? "__atomic_compare_exchange_n" :
        strcmp(name, "atomic_exchange") == 0 ? "__atomic_exchange_n" :
        strcmp(name, "atomic_fetch_add") == 0 ? "__atomic_fetch_add" :
        strcmp(name, "atomic_fetch_sub") == 0 ? "__atomic_fetch_sub" :
        strcmp(name, "atomic_fetch_and") == 0 ? "__atomic_fetch_and" :
        strcmp(name, "atomic_fetch_or") == 0 ? "__atomic_fetch_or" : "__atomic_fetch_xor";
    re0_buffer_write_fmt(out, "%s(__atomic_p%d", builtin, id);
    if (compare) re0_buffer_write_fmt(out, ", __atomic_expected%d", id);
    if (!load) re0_buffer_write_fmt(out, ", __atomic_value%d", id);
    if (compare) re0_buffer_write_str(out, ", false");
    re0_buffer_write_fmt(out, ", %s", order(e->call.args[count - (compare ? 2 : 1)]));
    if (compare) re0_buffer_write_fmt(out, ", %s", order(e->call.args[4]));
    re0_buffer_write_str(out, "); })");
}
