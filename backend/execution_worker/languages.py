"""Server-controlled language configuration (module §6). Candidate requests
select a language by name only — the actual compile/run commands always
come from this fixed dict, never from anything in the request body. This
is what "commands must come from server-controlled configuration, not
arbitrary shell commands from users" means structurally, not just by
convention: there is no code path anywhere in this service that builds a
command line from user-supplied strings.

`min_address_space_mb`/`min_process_limit` (Module 6 final-review fix):
some toolchains need meaningfully more RLIMIT_AS/RLIMIT_NPROC headroom
than a typical candidate program does, independent of the requested
memory_limit_mb — discovered by actually running javac/java/g++ under the
sandbox's real rlimits during a review pass, not by reasoning about it in
the abstract:
  - the JVM reserves virtual address space up front for its heap,
    metaspace, compressed-class-space, thread stacks, and JIT code cache
    that adds up to well over 1GB even for a trivial one-line program, and
    (confirmed empirically, not assumed) RLIMIT_AS interacts unreliably
    with the JVM's own memory-mapping behavior at tighter ceilings —
    javac failed with three *different* errors (compressed-class-space
    allocation, then a generic malloc failure) at 900MB/1024MB/1152MB
    across otherwise-identical runs. A generous, consistent ceiling
    (3GB) combined with explicit `-Xmx`/`-XX:MaxMetaspaceSize` heap caps
    (which bound *actual* usage, not virtual reservation) is what
    actually works reliably — verified across repeated trials.
  - the JVM also spawns 15-30+ internal threads (GC, JIT compiler, GC
    refinement) scaled to `Runtime.availableProcessors()`, which reports
    the *host's* full core count inside a container regardless of any
    cgroup CPU quota (confirmed: `nproc` inside this container reports 8,
    not the compose file's `cpus: 2.0`) — `-XX:ActiveProcessorCount=1`
    caps this at the source; RLIMIT_NPROC still needs real headroom on
    top of that for compilation specifically.
  - g++ itself forks a `cc1plus` compiler-backend subprocess (and an
    assembler); the default 32-process budget was too tight for that
    subprocess spawn alone, independent of anything Java-specific
    (verified directly: `cc1plus`/`posix_spawn: Resource temporarily
    unavailable` at RLIMIT_NPROC=32/48, consistently succeeds at 64+).
0 (the default) means "no override — use the request's own limits",
matching the original Python/C++-only behavior exactly for every language
that doesn't need this.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageConfig:
    identifier: str
    display_name: str
    source_filename: str
    compile_cmd: list[str] | None  # None = no compilation step (interpreted language)
    run_cmd: list[str]
    version_check_cmd: list[str]
    min_address_space_mb: int = 0
    min_process_limit: int = 0


LANGUAGE_CONFIGS: dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        identifier="python",
        display_name="Python 3",
        source_filename="solution.py",
        compile_cmd=None,
        run_cmd=["python3", "solution.py"],
        version_check_cmd=["python3", "--version"],
    ),
    "java": LanguageConfig(
        identifier="java",
        display_name="Java 17",
        # The public class must be named Solution — the candidate's source
        # is always written to this exact filename; a mismatched class name
        # simply fails to compile, same as any real Java toolchain.
        source_filename="Solution.java",
        # -J-... passes a flag to javac's OWN JVM (as opposed to a flag
        # that would apply to code javac is compiling). ActiveProcessorCount
        # caps the JVM's internal thread scaling (see module docstring);
        # Xmx/MaxMetaspaceSize are real, enforced heap/metadata caps — the
        # actual memory bound, now that RLIMIT_AS itself has to be loose.
        compile_cmd=[
            "javac",
            "-J-Xmx256m",
            "-J-XX:MaxMetaspaceSize=128m",
            "-J-XX:ActiveProcessorCount=1",
            "Solution.java",
        ],
        run_cmd=[
            "java",
            "-Xmx256m",
            "-XX:MaxMetaspaceSize=128m",
            "-XX:ActiveProcessorCount=1",
            "Solution",
        ],
        version_check_cmd=["java", "--version"],
        min_address_space_mb=3072,
        min_process_limit=112,
    ),
    "cpp": LanguageConfig(
        identifier="cpp",
        display_name="C++ (g++ 17)",
        source_filename="solution.cpp",
        compile_cmd=["g++", "-O2", "-std=c++17", "-o", "solution", "solution.cpp"],
        run_cmd=["./solution"],
        version_check_cmd=["g++", "--version"],
        min_process_limit=96,
    ),
}


def is_supported(language: str) -> bool:
    return language in LANGUAGE_CONFIGS


def get_language_config(language: str) -> LanguageConfig:
    try:
        return LANGUAGE_CONFIGS[language]
    except KeyError:
        raise ValueError(f"unsupported language: {language!r}") from None
