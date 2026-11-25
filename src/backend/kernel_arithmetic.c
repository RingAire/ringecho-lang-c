#include "backend/kernel_arithmetic.h"
#include "backend/backend_c_internal.h"

/* Operation values are local to the freestanding helper ABI. */
typedef enum {
    KERNEL_ADD, KERNEL_SUB, KERNEL_MUL, KERNEL_DIV, KERNEL_MOD,
    KERNEL_SHL, KERNEL_SHR
} KernelOperation;

static void lowering_error(Re0Codegen *c, Re0Expr *expression, const char *message) {
    re0_error_append(c->errors, RE0_ERR_SEMANTIC, expression->span, NULL,
                     "kernel integer lowering: %s", message);
    c->had_error = true;
}

static int operation(Re0BinOpKind op) {
    switch (op) {
        case BINOP_ADD: return KERNEL_ADD;
        case BINOP_SUB: return KERNEL_SUB;
        case BINOP_MUL: return KERNEL_MUL;
        case BINOP_DIV: return KERNEL_DIV;
        case BINOP_MOD: return KERNEL_MOD;
        case BINOP_SHL: return KERNEL_SHL;
        case BINOP_SHR: return KERNEL_SHR;
        default: return -1;
    }
}

/* One template for the 64-bit and optional 128-bit carriers. Every shift is
 * bounded, all arithmetic on bit patterns is unsigned, and signed decoding
 * casts only representable values. Restoring division handles the carry bit
 * explicitly, including divisors larger than half the carrier range. */
static void emit_carrier(Re0Buffer *out, const char *suffix,
                         const char *unsigned_type, const char *signed_type,
                         unsigned width) {
    re0_buffer_write_fmt(out,
        "typedef %s __reo_kernel_u%s;\n"
        "typedef %s __reo_kernel_s%s;\n"
        "static __reo_kernel_u%s __reo_kernel_mask%s(unsigned bits) {\n"
        "    if (!(bits == 8 || bits == 16 || bits == 32 || bits == 64%s)) __reo_kernel_fail();\n"
        "    return bits == %u ? ~(__reo_kernel_u%s)0 : (((__reo_kernel_u%s)1 << bits) - 1);\n"
        "}\n",
        unsigned_type, suffix, signed_type, suffix, suffix, suffix,
        width == 128 ? " || bits == 128" : "", width, suffix, suffix);
    re0_buffer_write_fmt(out,
        "static __reo_kernel_s%s __reo_kernel_signed%s(__reo_kernel_u%s value, unsigned bits) {\n"
        "    __reo_kernel_u%s mask = __reo_kernel_mask%s(bits); value &= mask;\n"
        "    if (value & ((__reo_kernel_u%s)1 << (bits - 1)))\n"
        "        return -1 - (__reo_kernel_s%s)(mask - value);\n"
        "    return (__reo_kernel_s%s)value;\n"
        "}\n",
        suffix, suffix, suffix, suffix, suffix, suffix, suffix, suffix);
    re0_buffer_write_fmt(out,
        "static __reo_kernel_u%s __reo_kernel_divrem%s(__reo_kernel_u%s a, __reo_kernel_u%s b, bool remainder) {\n"
        "    if (!b) __reo_kernel_fail();\n"
        "    __reo_kernel_u%s q = 0, r = 0;\n"
        "    for (unsigned i = %u; i > 0; --i) {\n"
        "        bool carry = (r >> %u) != 0;\n"
        "        r = (r << 1) | ((a >> (i - 1)) & 1);\n"
        "        if (carry || r >= b) { r -= b; q |= (__reo_kernel_u%s)1 << (i - 1); }\n"
        "    }\n"
        "    return remainder ? r : q;\n"
        "}\n",
        suffix, suffix, suffix, suffix, suffix, width, width - 1, suffix);
    re0_buffer_write_fmt(out,
        "static __reo_kernel_u%s __reo_kernel_binary%s(__reo_kernel_u%s a, __reo_kernel_u%s b, unsigned bits, bool signed_type, unsigned op) {\n"
        "    __reo_kernel_u%s mask = __reo_kernel_mask%s(bits); a &= mask; b &= mask;\n"
        "    if (op == %d) return (a + b) & mask;\n"
        "    if (op == %d) return (a - b) & mask;\n"
        "    if (op == %d) return (a * b) & mask;\n"
        "    unsigned shift = (unsigned)(b & (bits - 1));\n"
        "    if (op == %d) return (a << shift) & mask;\n"
        "    __reo_kernel_u%s sign = (__reo_kernel_u%s)1 << (bits - 1);\n"
        "    if (op == %d) {\n"
        "        __reo_kernel_u%s result = a >> shift;\n"
        "        if (signed_type && shift && (a & sign)) result |= mask ^ (mask >> shift);\n"
        "        return result;\n"
        "    }\n"
        "    if (op != %d && op != %d) __reo_kernel_fail();\n"
        "    if (!b || (signed_type && a == sign && b == mask)) __reo_kernel_fail();\n"
        "    bool negative_a = signed_type && (a & sign);\n"
        "    bool negative_b = signed_type && (b & sign);\n"
        "    __reo_kernel_u%s magnitude_a = negative_a ? (0 - a) & mask : a;\n"
        "    __reo_kernel_u%s magnitude_b = negative_b ? (0 - b) & mask : b;\n"
        "    __reo_kernel_u%s result = __reo_kernel_divrem%s(magnitude_a, magnitude_b, op == %d);\n"
        "    bool negative = op == %d ? negative_a : negative_a != negative_b;\n"
        "    return (negative ? 0 - result : result) & mask;\n"
        "}\n",
        suffix, suffix, suffix, suffix, suffix, suffix,
        KERNEL_ADD, KERNEL_SUB, KERNEL_MUL, KERNEL_SHL,
        suffix, suffix, KERNEL_SHR, suffix, KERNEL_DIV, KERNEL_MOD,
        suffix, suffix, suffix, suffix, KERNEL_MOD, KERNEL_MOD);
}

void re0_kernel_arithmetic_emit(Re0Buffer *out) {
    if (!out) return;
    emit_carrier(out, "64", "uint64_t", "int64_t", 64);
    re0_buffer_write_str(out,
        "#if defined(__SIZEOF_INT128__)\n"
        "__extension__ typedef unsigned __int128 __reo_u128;\n"
        "__extension__ typedef __int128 __reo_i128;\n");
    emit_carrier(out, "128", "__reo_u128", "__reo_i128", 128);
    re0_buffer_write_str(out, "#endif\n");
}

static void emit_call(Re0Codegen *c, Re0TypeKind kind, int op,
                      Re0Expr *left, Re0Expr *right) {
    bool wide = kind == RE0_TYPE_I128 || kind == RE0_TYPE_U128;
    bool sign = re0_type_is_signed(kind);
    const char *suffix = wide ? "128" : "64";
    const char *type = reo_type_to_c(re0_type_kind_name(kind));
    re0_buffer_write_fmt(&c->output, "((%s)(", type);
    if (sign) re0_buffer_write_fmt(&c->output, "__reo_kernel_signed%s(", suffix);
    re0_buffer_write_fmt(&c->output, "__reo_kernel_binary%s((__reo_kernel_u%s)(", suffix, suffix);
    if (left) c_gen_expr(c, left); else re0_buffer_write_str(&c->output, "0");
    re0_buffer_write_fmt(&c->output, "), (__reo_kernel_u%s)(", suffix);
    c_gen_expr(c, right);
    re0_buffer_write_fmt(&c->output, "), sizeof(%s) * CHAR_BIT, %s, %d)", type, sign ? "true" : "false", op);
    if (sign) re0_buffer_write_fmt(&c->output, ", sizeof(%s) * CHAR_BIT)", type);
    re0_buffer_write_str(&c->output, "))");
}

void re0_kernel_binary_emit(Re0Codegen *c, Re0Expr *expression) {
    if (!c || !expression) return;
    Re0TypeKind kind = c_expr_scalar_kind(expression);
    int op = expression->kind == EXPR_BINARY ? operation(expression->binary.op) : -1;
    if (!re0_type_is_integer(kind) || op < 0 || !expression->binary.left || !expression->binary.right) {
        lowering_error(c, expression, "invalid binary operation"); return;
    }
    emit_call(c, kind, op, expression->binary.left, expression->binary.right);
}

void re0_kernel_negate_emit(Re0Codegen *c, Re0Expr *expression) {
    if (!c || !expression) return;
    Re0TypeKind kind = c_expr_scalar_kind(expression);
    if (expression->kind != EXPR_UNARY || expression->unary.op != UNOP_NEG ||
        !re0_type_is_signed(kind) || !expression->unary.operand) {
        lowering_error(c, expression, "invalid negation"); return;
    }
    emit_call(c, kind, KERNEL_SUB, NULL, expression->unary.operand);
}

void re0_kernel_integer_cast_emit(Re0Codegen *c, Re0Expr *expression) {
    if (!c || !expression) return;
    Re0TypeKind kind = c_expr_scalar_kind(expression);
    if (expression->kind != EXPR_CAST || expression->cast.checked ||
        !re0_type_is_integer(kind) || !expression->cast.inner) {
        lowering_error(c, expression, "invalid integer cast"); return;
    }
    const char *type = reo_type_to_c(re0_type_kind_name(kind));
    const char *suffix = kind == RE0_TYPE_I128 || kind == RE0_TYPE_U128 ? "128" : "64";
    bool sign = re0_type_is_signed(kind);
    re0_buffer_write_fmt(&c->output, "((%s)(", type);
    if (sign) re0_buffer_write_fmt(&c->output, "__reo_kernel_signed%s((__reo_kernel_u%s)(", suffix, suffix);
    c_gen_expr(c, expression->cast.inner);
    if (sign) re0_buffer_write_fmt(&c->output, "), sizeof(%s) * CHAR_BIT)", type);
    re0_buffer_write_str(&c->output, "))");
}
