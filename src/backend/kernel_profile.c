#include "backend/kernel_profile.h"
#include "backend/kernel_arithmetic.h"
#include "backend/kernel_runtime.h"

/* Text of the self-contained kernel-profile prelude. See kernel_profile.h for
 * the contract. The generated C is compiled with `-ffreestanding -nostdlib`,
 * so every host-libc name it references is bound here to a freestanding
 * stand-in (weak kernel hooks + tiny local helpers). */
static const char KERNEL_PRELUDE[] =
    "/* --- RingEcho kernel profile prelude (self-contained, no host libc) --- */\n"
    "#include <stdint.h>\n#include <stdbool.h>\n#include <stddef.h>\n"
    "#include <limits.h>\n#include <float.h>\n"
    "#define isnan(x) __builtin_isnan(x)\n"
    "#define isfinite(x) __builtin_isfinite(x)\n"
    "#define INFINITY (__builtin_inff())\n"
    "#define NAN (__builtin_nanf(\"\"))\n"
    "double strtod(const char *, char **);\n"
    "int snprintf(char *, size_t, const char *, ...);\n"
    /* LLVM may introduce these calls after C-level dead-code elimination,
     * e.g. for a large by-value union. Retain their local definitions. */
    "__attribute__((used)) static void *memcpy(void *d, const void *s, size_t n) { unsigned char *a = (unsigned char *)d; const unsigned char *b = (const unsigned char *)s; while (n--) *a++ = *b++; return d; }\n"
    "__attribute__((used)) static void *memset(void *d, int c, size_t n) { unsigned char *a = (unsigned char *)d; while (n--) *a++ = (unsigned char)c; return d; }\n"
    "__attribute__((used)) static void *memmove(void *d, const void *s, size_t n) { if (!n || d == s) return d; unsigned char *a = (unsigned char *)d; const unsigned char *b = (const unsigned char *)s; if ((uintptr_t)a < (uintptr_t)b) { while (n--) *a++ = *b++; } else { a += n; b += n; while (n--) *--a = *--b; } return d; }\n"
    "static int memcmp(const void *x, const void *y, size_t n) { const unsigned char *a = (const unsigned char *)x; const unsigned char *b = (const unsigned char *)y; while (n--) { if (*a != *b) return (int)*a - (int)*b; a++; b++; } return 0; }\n"
    "static int strcmp(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return (int)(unsigned char)*a - (int)(unsigned char)*b; }\n"
    "typedef struct { int64_t tag; union { int64_t v0; } u; } Option;\n"
    "typedef struct { int64_t tag; union { int64_t v0; } u; } Result;\n"
    "#define __REO_CONV_ALLOC malloc\n"
    "#define __REO_CONV_FREE free\n"
    "#define __REO_FREESTANDING 1\n";

/* Sequence/bounds support; integer helpers live in kernel_arithmetic. The
 * hosted string/float conversion runtime is not included. */
static const char KERNEL_RUNTIME[] =
    "__extension__ typedef struct {} __reo_unit;\n"
    "enum { __REO_CONV_FORMAT = 1, __REO_CONV_RANGE, __REO_CONV_NONFINITE,\n"
    "       __REO_CONV_LENGTH, __REO_CONV_MEMORY, __REO_CONV_MAX_TEXT = 4096 };\n"
    "static void __reo_null_call(void) { __reo_kernel_fail_message(\"null function pointer\"); }\n"
    "static void __reo_sequence_error(void) { __reo_kernel_fail_message(\"invalid sequence size or allocation failure\"); }\n"
    "static size_t __reo_check_index(int64_t index, size_t length) { if (index < 0 || (uint64_t)index >= length) __reo_kernel_fail_message(\"array index out of bounds\"); return (size_t)index; }\n"
    "static void *__reo_sequence_alloc(size_t bytes) { void *p = malloc(bytes); if (!p && bytes) __reo_sequence_error(); return p; }\n";

void re0_kernel_prelude_emit(Re0Buffer *out) {
    if (!out) return;
    re0_buffer_write_str(out, KERNEL_PRELUDE);
    re0_kernel_hooks_emit(out);
}

static const char KERNEL_IO[] =
    "#if defined(__i386__) || defined(__x86_64__)\n"
    "static inline uint8_t __reo_inb(uint16_t port) { uint8_t value; __asm__ __volatile__(\"inb %1, %0\" : \"=a\"(value) : \"Nd\"(port)); return value; }\n"
    "static inline uint16_t __reo_inw(uint16_t port) { uint16_t value; __asm__ __volatile__(\"inw %1, %0\" : \"=a\"(value) : \"Nd\"(port)); return value; }\n"
    "static inline uint32_t __reo_inl(uint16_t port) { uint32_t value; __asm__ __volatile__(\"inl %1, %0\" : \"=a\"(value) : \"Nd\"(port)); return value; }\n"
    "static inline void __reo_outb(uint16_t port, uint8_t value) { __asm__ __volatile__(\"outb %0, %1\" : : \"a\"(value), \"Nd\"(port)); }\n"
    "static inline void __reo_outw(uint16_t port, uint16_t value) { __asm__ __volatile__(\"outw %0, %1\" : : \"a\"(value), \"Nd\"(port)); }\n"
    "static inline void __reo_outl(uint16_t port, uint32_t value) { __asm__ __volatile__(\"outl %0, %1\" : : \"a\"(value), \"Nd\"(port)); }\n"
    "static inline void __reo_cli(void) { __asm__ __volatile__(\"cli\" ::: \"memory\"); }\n"
    "static inline void __reo_sti(void) { __asm__ __volatile__(\"sti\" ::: \"memory\"); }\n"
    "static inline void __reo_hlt(void) { __asm__ __volatile__(\"hlt\"); }\n"
    "static inline void __reo_load_idt(uint16_t limit, const void *base) { struct __attribute__((packed)) { uint16_t limit; uintptr_t base; } idtr = { limit, (uintptr_t)base }; __asm__ __volatile__(\"lidt %0\" : : \"m\"(idtr)); }\n"
    "static inline void __reo_halt_forever(void) { __reo_cli(); for (;;) __reo_hlt(); }\n"
    "#else\n"
    "static inline uint8_t __reo_inb(uint16_t port) { (void)port; return 0; }\n"
    "static inline uint16_t __reo_inw(uint16_t port) { (void)port; return 0; }\n"
    "static inline uint32_t __reo_inl(uint16_t port) { (void)port; return 0; }\n"
    "static inline void __reo_outb(uint16_t port, uint8_t value) { (void)port; (void)value; }\n"
    "static inline void __reo_outw(uint16_t port, uint16_t value) { (void)port; (void)value; }\n"
    "static inline void __reo_outl(uint16_t port, uint32_t value) { (void)port; (void)value; }\n"
    "static inline void __reo_cli(void) { }\n"
    "static inline void __reo_sti(void) { }\n"
    "static inline void __reo_hlt(void) { }\n"
    "static inline void __reo_load_idt(uint16_t limit, const void *base) { (void)limit; (void)base; }\n"
    "static inline void __reo_halt_forever(void) { for (;;) { } }\n"
    "static const char* __reo_getenv(const char* name) { (void)name; return \"\"; }\n"
    "static bool __reo_file_exists(const char* path) { (void)path; return false; }\n"
    "static bool __reo_file_remove(const char* path) { (void)path; return false; }\n"
    "static bool __reo_file_rename(const char* from, const char* to) { (void)from; (void)to; return false; }\n"
    "static bool __reo_dir_create(const char* path) { (void)path; return false; }\n"
    "static int32_t __reo_proc_spawn(const char* program, const char* const* args, size_t count) { (void)program; (void)args; (void)count; return -1; }\n"
    "#endif\n"
    ;

void re0_kernel_runtime_emit(Re0Buffer *out) {
    if (!out) return;
    re0_buffer_write_str(out, KERNEL_RUNTIME);
    re0_buffer_write_str(out, KERNEL_IO);
    re0_kernel_arithmetic_emit(out);
}
