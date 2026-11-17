// Runs a program and reports how long it took and how much memory it used.
//
// Usage: algebra_measure OUTPUT_FILE program [arguments...]
//
// The program's output goes to OUTPUT_FILE. When it ends, one line is printed:
//   wall_seconds user_seconds system_seconds peak_rss_kib exit_code
//
// Peak memory is the kernel's maximum resident set size for the child process.
// That figure can never be lower than the memory of the process that started
// the child, so a launcher written in Python would hide anything below about
// 15 MB. This launcher is a separate program that uses about 1 MB.

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "Usage: %s OUTPUT_FILE program [arguments...]\n", argv[0]);
        return 64;
    }
    const auto start = std::chrono::steady_clock::now();
    const pid_t child = fork();
    if (child < 0) {
        std::perror("fork");
        return 71;
    }
    if (child == 0) {
        const int output = open(argv[1], O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (output < 0) {
            std::perror(argv[1]);
            _exit(73);
        }
        dup2(output, STDOUT_FILENO);
        dup2(output, STDERR_FILENO);
        close(output);
        execvp(argv[2], argv + 2);
        std::perror(argv[2]);
        _exit(127);
    }
    int status = 0;
    struct rusage usage {};
    if (wait4(child, &status, 0, &usage) < 0) {
        std::perror("wait4");
        return 71;
    }
    const double wall =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    const double user = static_cast<double>(usage.ru_utime.tv_sec) +
                        static_cast<double>(usage.ru_utime.tv_usec) / 1e6;
    const double system = static_cast<double>(usage.ru_stime.tv_sec) +
                          static_cast<double>(usage.ru_stime.tv_usec) / 1e6;
    long peak_kib = usage.ru_maxrss;
#ifdef __APPLE__
    peak_kib /= 1024;   // macOS reports bytes
#endif
    const int exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    std::printf("%.3f %.3f %.3f %ld %d\n", wall, user, system, peak_kib, exit_code);
    return 0;
}
