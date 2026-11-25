#include "exec/process.h"
#include "platform.h"
#include <errno.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RE0_PROCESS_MAX_ARGUMENTS 128
#define RE0_PROCESS_MAX_COMMAND 32767

#if defined(RE0_PLATFORM_WINDOWS)
#include <windows.h>

static bool append_char(char *buffer, size_t *length, char value) {
    if (*length >= RE0_PROCESS_MAX_COMMAND - 1) return false;
    buffer[(*length)++] = value;
    return true;
}

static bool append_argument(char *buffer, size_t *length, const char *argument) {
    if (!append_char(buffer, length, '"')) return false;
    const char *p = argument;
    for (;;) {
        size_t slashes = 0;
        while (*p == '\\') { slashes++; p++; }
        size_t count = (*p == '"' || !*p) ? slashes * 2 : slashes;
        for (size_t i = 0; i < count; i++)
            if (!append_char(buffer, length, '\\')) return false;
        if (!*p) break;
        if (*p == '"' && !append_char(buffer, length, '\\')) return false;
        if (!append_char(buffer, length, *p++)) return false;
    }
    return append_char(buffer, length, '"');
}
#else
#include <unistd.h>
#include <sys/wait.h>
#endif

#if defined(RE0_PLATFORM_WINDOWS)
/* A bare program name must never resolve through the current directory:
 * a cloned project could ship gcc.exe/clang.exe and get code execution. */
static bool has_path_component(const char *program) {
    if (!program || !*program) return false;
    if (program[0] && program[1] == ':') return true;
    return strchr(program, '/') != NULL || strchr(program, '\\') != NULL;
}

static bool is_executable_file(const char *path) {
    DWORD attributes = GetFileAttributesA(path);
    return attributes != INVALID_FILE_ATTRIBUTES &&
           !(attributes & FILE_ATTRIBUTE_DIRECTORY);
}

static bool join_candidate(char *out, size_t cap, const char *dir,
                           const char *program, bool add_exe) {
    int written = snprintf(out, cap, add_exe ? "%s\\%s.exe" : "%s\\%s", dir, program);
    return written >= 0 && (size_t)written < cap;
}

static bool resolve_program(const char *program, char *out, size_t cap) {
    if (!program || !*program) return false;
    if (has_path_component(program)) {
        if (snprintf(out, cap, "%s", program) < 0) return false;
        return is_executable_file(out);
    }

    const bool want_exe = strlen(program) < 4 ||
                          _stricmp(program + strlen(program) - 4, ".exe") != 0;
    char candidate[1024];

    /* The directory containing this executable is trusted. */
    char module[1024];
    DWORD length = GetModuleFileNameA(NULL, module, (DWORD)sizeof(module));
    if (length > 0 && length < sizeof(module)) {
        char *slash = strrchr(module, '\\');
        if (slash) {
            *slash = '\0';
            if (want_exe && join_candidate(candidate, sizeof(candidate), module, program, true) &&
                is_executable_file(candidate)) {
                snprintf(out, cap, "%s", candidate);
                return true;
            }
            if (join_candidate(candidate, sizeof(candidate), module, program, false) &&
                is_executable_file(candidate)) {
                snprintf(out, cap, "%s", candidate);
                return true;
            }
        }
    }

    const char *path = getenv("PATH");
    if (!path) return false;
    while (*path) {
        const char *end = strchr(path, ';');
        size_t entry_length = end ? (size_t)(end - path) : strlen(path);
        char dir[1024];
        if (entry_length > 0 && entry_length < sizeof(dir)) {
            memcpy(dir, path, entry_length);
            dir[entry_length] = '\0';
            if (dir[0] == '"' && entry_length >= 2 && dir[entry_length - 1] == '"') {
                memmove(dir, dir + 1, entry_length - 2);
                dir[entry_length - 2] = '\0';
            }
            const bool absolute = (dir[0] == '\\' && dir[1] == '\\') ||
                                  (((dir[0] >= 'A' && dir[0] <= 'Z') ||
                                    (dir[0] >= 'a' && dir[0] <= 'z')) && dir[1] == ':');
            if (absolute) {
                if (want_exe && join_candidate(candidate, sizeof(candidate), dir, program, true) &&
                    is_executable_file(candidate)) {
                    snprintf(out, cap, "%s", candidate);
                    return true;
                }
                if (join_candidate(candidate, sizeof(candidate), dir, program, false) &&
                    is_executable_file(candidate)) {
                    snprintf(out, cap, "%s", candidate);
                    return true;
                }
            }
        }
        if (!end) break;
        path = end + 1;
    }
    return false;
}
#endif

int re0_process_run(const char *program, const char *const arguments[]) {
    if (!program || !*program || !arguments || !arguments[0]) return -1;
    size_t count = 0;
    while (count < RE0_PROCESS_MAX_ARGUMENTS && arguments[count]) count++;
    if (count == RE0_PROCESS_MAX_ARGUMENTS) return -1;
#if defined(RE0_PLATFORM_WINDOWS)
    char resolved[1024];
    if (!resolve_program(program, resolved, sizeof(resolved))) return -1;
    char *command = malloc(RE0_PROCESS_MAX_COMMAND);
    if (!command) return -1;
    size_t length = 0;
    bool ok = true;
    for (size_t i = 0; i < count && ok; i++) {
        if (i) ok = append_char(command, &length, ' ');
        if (ok) ok = append_argument(command, &length, arguments[i]);
    }
    command[length] = 0;
    STARTUPINFOA startup = {0};
    PROCESS_INFORMATION process = {0};
    startup.cb = sizeof(startup);
    BOOL launched = ok && CreateProcessA(resolved, command, NULL, NULL, FALSE, 0,
                                         NULL, NULL, &startup, &process);
    free(command);
    if (!launched) return -1;
    DWORD exit_code = 0;
    DWORD waited = WaitForSingleObject(process.hProcess, INFINITE);
    BOOL obtained = waited == WAIT_OBJECT_0 && GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return obtained && exit_code <= 2147483647UL ? (int)exit_code : -1;
#else
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        execvp(program, (char *const *)arguments);
        _exit(127);
    }
    int status = 0;
    pid_t waited;
    do { waited = waitpid(pid, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited < 0) return -1;
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + WTERMSIG(status);
    return -1;
#endif
}
