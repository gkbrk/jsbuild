#!/usr/bin/env python3

# jsbuild: Javascript builder and package manager
# Copyright 2021-2022 Gokberk Yaltirakli
# SPDX-License-Identifier: Apache-2.0

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

NAME = "jsbuild"
VERSION = "0.0.1"
VERBOSE = False

# Logging


def log(line):
    """Log a line to stderr.

    This function prints a log message to stderr if VERBOSE is enabled. The log
    line is prefixed by the timestamp.

    Parameters
    ----------
    line : str
        The line to print.

    Returns
    -------
    None

    """
    if not VERBOSE:
        return
    s = time.strftime("%H:%M:%S")
    s = f"[{s}] {line}\n"
    s = s.encode("utf-8")
    sys.stderr.buffer.write(s)
    sys.stderr.buffer.flush()


# Custom hash function because why not


def triple32(x):
    x ^= x >> 17
    x *= 0xED5AD4BB
    x &= 0xFFFFFFFF

    x ^= x >> 11
    x *= 0xAC4C1B51
    x &= 0xFFFFFFFF

    x ^= x >> 15
    x *= 0x31848BAB
    x &= 0xFFFFFFFF

    x ^= x >> 14
    return x


def triple32_buf(buf):
    h = triple32(1)

    # Two rounds is enough for anybody
    for _ in range(2):
        for c in buf:
            h = triple32(h ^ c)

    return h


def hash_value(val, size=16):
    result = bytearray(size)

    val_len = len(val)

    buf = len(val).to_bytes(2, "big") + val

    for i in range(size):
        h = triple32_buf(buf + i.to_bytes(1, "big"))
        result[i] = h & 0xFF

    return result


# File system cache

def cache_dir():
    xdg = os.environ.get("XDG_CACHE_HOME")
    home = os.path.expanduser("~/.cache")
    path = Path(xdg or home) / NAME
    os.makedirs(path, exist_ok=True)
    return path


CACHE_DIR = cache_dir()


def cache_path(key):
    try:
        key = key.encode("utf-8")
    except:
        pass

    hash = hash_value(key)
    return CACHE_DIR / hash.hex()


# HTTP

USER_AGENT = f"{NAME}/{VERSION} (+https://www.gkbrk.com/project/{NAME})"


def http_cache_or_download(url):
    path = cache_path(f"http_{url}")

    try:
        return path.read_bytes().decode("utf-8")
    except:
        pass

    subprocess.run(["curl", "--user-agent", USER_AGENT, "-o", path, "-s", url])
    return path.read_bytes().decode("utf-8")


# File imports / import schemes

# Importing based on different schemas (like file:// and http://) are handled
# here.


def read_file_file(url):
    p = Path(url.path)
    return p.read_bytes().decode("utf-8")


def read_file_http(url):
    return http_cache_or_download(urlunparse(url))


def read_file(url):
    return globals()[f"read_file_{url.scheme}"](url)


# Relative and absolute URLs


def resolve_absolute(current, new):
    merged = urljoin(current, new)
    return urlparse(merged)


# Closure compiler

ver = "v20211107"
CLOSURE_URL = f"https://repo1.maven.org/maven2/com/google/javascript/closure-compiler/{ver}/closure-compiler-{ver}.jar"
CLOSURE = cache_path(CLOSURE_URL)


def closure_compile(path):
    params = []

    # Run the CLOSURE jar file
    params.append("java")
    params.append("-jar")
    params.append(cache_path(CLOSURE_URL))

    # Include the imports directory
    params.append("--js")
    params.append("imports/*.js")

    # Optimization parameters
    params.append("-O")
    params.append("ADVANCED")
    params.append("--assume_function_wrapper")
    params.append("--use_types_for_optimization")
    params.append("--dependency_mode")
    params.append("PRUNE")

    # Output
    params.append("--language_out")
    params.append("ECMASCRIPT_2019")

    # HTML Output
    # TODO: Make this a command line flag
    # params.append("--output_wrapper")
    # params.append('<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body><script>(async function() {%output%}).call(this);</script></body></html>')

    # Entry point
    params.append("--js")
    params.append("main.js")
    params.append("--entry_point")
    params.append("main.js")

    proc = subprocess.run(params, cwd=path, capture_output=True)
    log(proc.stderr.decode("utf-8"))
    return proc.stdout.decode("utf-8")


# Deps


def import_statements_recursive(url):
    content = read_file(url)

    for line in content.split("\n"):
        m = re.match('^import .*? from "(.*?)";$', line)
        if m:
            new_url = resolve_absolute(urlunparse(url), m.group(1))
            yield url, new_url
            yield from import_statements_recursive(new_url)


def patch_import_statement(line, current_path, inside_import=False):
    m = re.match('^import (.*?) from "(.*?)";$', line)
    if m:
        url = m.group(2)
        url = resolve_absolute(current_path, url)
        url = str(url).encode("utf-8")
        h = hash_value(url).hex()
        if inside_import:
            return f'import {m.group(1)} from "./{h}.js";'
        else:
            return f'import {m.group(1)} from "./imports/{h}.js";'
    return line


# Actions / commands
# ==================

# Each action is defined by a function named `action_NameOfAction`. The main
# function checks its sub-command argument and executes the top-level-function
# based on name.

# If there is no default argument, the `help` function is executed. This
# function finds all the top-level actions and prints their doc-strings.


def action_help():
    """
    Displays this help message.
    """

    print(f"{NAME} v{VERSION} - Javascript build system")
    print()
    print(f"Usage: {EXE_NAME} command [ARGS...]")
    print()

    actions = lambda x: x.startswith("action_")
    actions = filter(actions, globals())
    for gl in sorted(actions):
        action = globals()[gl]
        print(gl[7:].replace("_", "-"))
        doc = "This command is not documented yet."

        if action.__doc__:
            doc = action.__doc__.strip()

        for line in doc.split("\n"):
            print(f"    {line.strip()}")
        print()


def action_list_deps():
    """Prints the list of dependencies that are included by your program. Note
    that the output of this command includes the dependencies recursively.

    """
    path = Path(sys.argv.pop(0))

    printed = set()

    for _, s in import_statements_recursive(
        urlparse(f"file://{path.resolve()}")
    ):
        s = urlunparse(s)
        if s not in printed:
            print(hash_value(s.encode("utf-8")).hex(), s)
        printed.add(s)


def action_dependency_dag():
    """Draws a Directed Acyclic Graph of the dependency tree.

    This requires `Graphviz` to generate the tree image and `feh` to display it on
    the screen.

    """
    path = Path(sys.argv.pop(0)).resolve()
    url = f"file://{path}"
    _url = url
    url = urlparse(url)

    dot_file = ""

    deps = set()
    for src, target in import_statements_recursive(url):
        deps.add((urlunparse(src), urlunparse(target)))

    nodes = set()

    for x, y in deps:
        nodes.add(x)
        nodes.add(y)

    dot_file += "digraph {\n"
    dot_file += "graph [splines=true overlap=false];\n"

    for n in nodes:
        h = hash_value(n.encode("utf-8")).hex()
        shape = "box"

        # Mark imports fetched over HTTP in a different way
        if n.startswith("http://") or n.startswith("https://"):
            shape = "egg"

        attr = f'"{h}" [label = "{n}" shape="{shape}"'

        # Mark the build target in red to make the graph easier to read.
        if n == _url:
            attr += " color = red"

        attr += "];\n"
        dot_file += attr

    for source, target in deps:
        h_source = hash_value(source.encode("utf-8")).hex()
        h_target = hash_value(target.encode("utf-8")).hex()
        dot_file += f'"{h_target}" -> "{h_source}"\n'
    dot_file += "}\n"
    dot_file = dot_file.encode("utf-8")

    proc = subprocess.run(
        ["sfdp", "-Tpng", "-o/dev/stdout"], input=dot_file, capture_output=True
    )
    png = proc.stdout

    # TODO: Check if `feh` is installed. Perhaps we can have a list of image
    # viewer applications to try in order.
    subprocess.run(["feh", "-"], input=png, capture_output=True)


def action_ensure_closure():
    """
    Downloads or updates the Closure compiler.
    """
    subprocess.run(["curl", "-o", cache_path(CLOSURE_URL), CLOSURE_URL])


def action_build():
    """Fetches all the dependencies of the input file and builds it."""
    path = Path(sys.argv.pop(0)).resolve()

    output_path = None
    if sys.argv:
        output_path = Path(sys.argv.pop(0)).resolve()

    with (TEMPDIR / "main.js").open("w+") as main_file:
        log((TEMPDIR / "main.js").resolve())
        for line in path.open("r"):
            main_file.write(
                patch_import_statement(line, f"file://{path}") + "\n"
            )

    os.makedirs(TEMPDIR / "imports")
    imports = set()

    for _, url in import_statements_recursive(
        urlparse(f"file://{path.resolve()}")
    ):
        imports.add(url)

    for imp in imports:
        log(imp)
        url = str(imp).encode("utf-8")
        h = hash_value(url).hex()
        content = read_file(imp)

        with (TEMPDIR / "imports" / f"{h}.js").open("w+") as js_file:
            for line in content.split("\n"):
                js_file.write(
                    patch_import_statement(line, urlunparse(imp), True) + "\n"
                )

    # Check if we have the closure compiler
    if not CLOSURE.is_file():
        action_ensure_closure()

    output = closure_compile(TEMPDIR)

    if output_path:
        output_path.write_text(output)
    else:
        print(output)

    # subprocess.run(["find", TEMPDIR, "-type", "f", "-exec", "echo", "-- File: {}", ";", "-exec", "head", "{}", ";", "-exec", "echo", "", ";"])


# Main function


def main():
    globals()["EXE_NAME"] = sys.argv.pop(0)
    globals()["_TEMPDIR"] = tempfile.TemporaryDirectory(prefix=f"{NAME}-")
    globals()["TEMPDIR"] = Path(_TEMPDIR.name)

    try:
        action = sys.argv.pop(0)
        action = action.lower()
        action = action.replace("-", "_")
    except:
        action = "help"

    fn_name = f"action_{action}"
    if fn_name not in globals():
        action_help()
        print(f"Unknown action '{action.lower()}'")
        sys.exit(1)

    globals()[fn_name]()


if __name__ == "__main__":
    main()
