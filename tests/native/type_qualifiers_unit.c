#include "backend/backend_c_internal.h"
#include <stdio.h>

static bool conversions(void) {
    const struct { const char *from, *to; bool equal, coercible; } cases[] = {
        {"*mut u32", "*mut volatile u32", false, true},
        {"*mut volatile u32", "*mut u32", false, false},
        {"*mut volatile u32", "*const volatile u32", false, true},
        {"*const volatile u32", "*mut volatile u32", false, false},
        {"*mut volatile u32", "ptr", false, false},
        {"*mut *mut u32", "*mut *mut volatile u32", false, false},
        {"*mut *mut volatile u32", "*mut *mut u32", false, false},
        {"*mut *mut u32", "*mut volatile *mut u32", false, true},
        {"*mut volatile *mut u32", "*mut *mut u32", false, false},
        {"*mut volatile u32", "*volatile mut u32", true, true},
        {"&mut u32", "*mut volatile u32", false, true},
        {"&u32", "*mut volatile u32", false, false},
        {"fn(*mut u32)", "fn(*mut volatile u32)", false, false}
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        Re0Type *from = re0_type_parse(cases[i].from);
        Re0Type *to = re0_type_parse(cases[i].to);
        bool ok = from && to && re0_type_equal(from, to) == cases[i].equal
            && re0_type_coercible(from, to) == cases[i].coercible;
        re0_type_free_tree(from); re0_type_free_tree(to);
        if (!ok) { fprintf(stderr, "qualifier conversion failed: %s -> %s\n", cases[i].from, cases[i].to); return false; }
    }
    const char *invalid[] = {"*volatile", "*const", "*mut const u32", "*const mut u32", "*volatile volatile u32", "*mut mut u32"};
    for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
        Re0Type *t = re0_type_parse(invalid[i]);
        bool rejected = t == NULL;
        re0_type_free_tree(t);
        if (!rejected) { fprintf(stderr, "accepted malformed qualifier: %s\n", invalid[i]); return false; }
    }
    return true;
}

static bool spelling(void) {
    Re0ErrorList errors; re0_error_list_init(&errors);
    Re0SemanticModel model; re0_model_init(&model);
    Re0StmtVec declarations; Re0StmtVec_init(&declarations);
    Re0Codegen codegen; re0_codegen_init(&codegen, &errors, &model, &re0_backend_c);
    reset_c_state(); c_storage_begin(&codegen, &declarations);
    const struct { const char *source, *c; } cases[] = {
        {"*mut volatile u32", "uint32_t volatile*"},
        {"*const volatile u32", "uint32_t volatile const*"},
        {"*mut volatile *mut u32", "uint32_t* volatile*"},
        {"*mut *mut volatile u32", "uint32_t volatile**"},
        {"*mut volatile *const volatile u32", "uint32_t volatile const* volatile*"},
        {"*mut\tvolatile\tu32", "uint32_t volatile*"}
    };
    bool ok = true;
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        Re0Type *t = re0_type_parse(cases[i].source);
        const char *rendered = t ? c_storage_type(t) : NULL;
        if (!rendered || strcmp(rendered, cases[i].c) != 0) {
            fprintf(stderr, "wrong qualifier layer: %s -> %s\n", cases[i].source, rendered ? rendered : "NULL");
            ok = false;
        }
        re0_type_free_tree(t);
    }
    ok = ok && !codegen.had_error;
    re0_codegen_destroy(&codegen); re0_model_free(&model); re0_error_list_free(&errors);
    return ok;
}

static bool target_numeric_conversions(void) {
    /* 128-bit pointer fixture verifies independence from the host without
     * advertising an unimplemented RingISA code-generation target. */
    Re0TargetLayout wide = re0_target_x86_64_sysv;
    wide.pointer_size = wide.pointer_align = 16;
    const struct { const char *from, *to; bool narrow, normal, wide; } cases[] = {
        {"u64", "usize", false, true, true},
        {"usize", "u64", true, true, false},
        {"i64", "isize", false, true, true},
        {"isize", "i64", true, true, false},
        {"u32", "isize", false, true, true},
        {"usize", "i64", true, false, false},
        {"usize", "f64", true, false, false},
        {"isize", "f64", true, false, false},
        {"u128", "usize", false, false, true},
        {"usize", "u128", true, true, true}
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        Re0Type *from = re0_type_parse(cases[i].from), *to = re0_type_parse(cases[i].to);
        bool ok = from && to &&
            re0_type_coercible_on(&re0_target_x86_sysv, from, to) == cases[i].narrow &&
            re0_type_coercible_on(&re0_target_x86_64_sysv, from, to) == cases[i].normal &&
            re0_type_coercible_on(&wide, from, to) == cases[i].wide;
        re0_type_free_tree(from); re0_type_free_tree(to);
        if (!ok) { fprintf(stderr, "target conversion failed: %s -> %s\n", cases[i].from, cases[i].to); return false; }
    }
    return true;
}

int main(void) {
    if (!conversions() || !spelling() || !target_numeric_conversions()) return 1;
    puts("type qualifier identity, conversions and C spelling passed");
    return 0;
}
