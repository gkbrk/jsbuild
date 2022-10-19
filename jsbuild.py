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

import argparse
import hashlib
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

NAME = "jsbuild"
VERSION = "0.0.1"

# Logging

log_format = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=log_format)
logger = logging.getLogger(NAME)


def hash_buffer(buf: bytes) -> str:
    inner = hashlib.sha256(b"jsbuild" + buf).digest()
    outer = hashlib.sha256(b"jsbuild" + inner).digest()
    return outer.hex()


# Temp dir
_TEMPDIR = tempfile.TemporaryDirectory(prefix="jsbuild-")
TEMPDIR = Path(_TEMPDIR.name)

# File system cache


def cache_dir():
    # Let's figure out where to cache our files.
    cache = None

    # First, check if the user has specified a cache directory.
    cache = os.environ.get("XDG_CACHE_HOME")

    # If not, just chuck it in ~/.cache.
    if not cache:
        cache = os.path.expanduser("~/.cache")

    # We will put our cache in a subdirectory of the cache directory.
    path = Path(cache) / NAME

    # Create the directory if it doesn't exist.
    os.makedirs(path, exist_ok=True)
    return path


CACHE_DIR = cache_dir()


def cache_path(key: str) -> Path:
    key = key.encode("utf-8")
    return CACHE_DIR / hash_buffer(key)


# HTTP

USER_AGENT = f"{NAME}/{VERSION} (+https://www.gkbrk.com/project/{NAME})"


def http_cache_or_download(url: str) -> str:
    path = cache_path(f"http_{url}")

    try:
        return path.read_bytes().decode("utf-8")
    except Exception:
        pass

    logger.info(f"Downloading {url}...")
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
    logging.debug(f"Reading {urlunparse(url)}...")
    scheme = url.scheme
    handler_name = f"read_file_{scheme}"

    if handler_name not in globals():
        raise Exception(f"Unknown scheme: {scheme}")

    handler = globals()[handler_name]
    return handler(url)


# Relative and absolute URLs


def resolve_absolute(current, new):
    merged = urljoin(current, new)
    return urlparse(merged)


# Closure compiler URL

ver = "v20221004"
REPO = "https://repo1.maven.org/maven2"
PROJECT = "com/google/javascript/closure-compiler"
CLOSURE_URL = f"{REPO}/{PROJECT}/{ver}/closure-compiler-{ver}.jar"
CLOSURE = cache_path(CLOSURE_URL)


def java_check():
    try:
        res = subprocess.run([ARGS.java, "-version"], capture_output=True)
        assert res.returncode == 0
        logging.debug("Java is installed.")

        for line in res.stderr.decode("utf-8").splitlines():
            logging.debug(f"[java -version] {line.strip()}")
        return True
    except Exception:
        logging.error("Java is not installed. Please install Java.")
        sys.exit(1)


def closure_compile(path):
    java_check()  # Make sure Java is installed.

    params = []

    # Run the CLOSURE jar file
    params.append(ARGS.java)
    params.append("-jar")
    params.append(CLOSURE)

    # Include the imports directory
    params.append("--js")
    params.append("imports/*.js")

    # Optimization parameters
    params.append("-W")
    params.append("VERBOSE")
    params.append("--compilation_level")
    params.append("ADVANCED_OPTIMIZATIONS")
    params.append("--assume_function_wrapper")
    # params.append("--use_types_for_optimization")
    params.append("--isolation_mode")
    params.append("IIFE")
    params.append("--dependency_mode")
    params.append("PRUNE")

    # Output
    params.append("--language_out")
    params.append(ARGS.language_out)

    # Entry point
    params.append("--js")
    params.append("main.js")
    params.append("--entry_point")
    params.append("main.js")

    proc = subprocess.run(params, cwd=path, capture_output=True)

    for err_line in proc.stderr.decode("utf-8").splitlines():
        logging.warn(f"[closure] {err_line.strip()}")
    return proc.stdout.decode("utf-8")


# Deps


def import_statements_recursive(url):
    content = read_file(url)

    for line in content.split("\n"):
        # TODO: Accept single-quotes as well
        m = re.match('^import .*? from "(.*?)";$', line)
        if m:
            new_url = resolve_absolute(urlunparse(url), m.group(1))
            yield url, new_url
            yield from import_statements_recursive(new_url)


def patch_import_statement(line, current_path, inside_import=False):
    # TODO: Accept single-quotes as well
    m = re.match('^import (.*?) from "(.*?)";$', line)
    if m:
        url = m.group(2)
        url = resolve_absolute(current_path, url)
        url = str(url).encode("utf-8")
        h = hash_buffer(url)
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


def action_list_deps():
    """Prints the list of dependencies that are included by your program. Note
    that the output of this command includes the dependencies recursively.

    """
    path = Path(ARGS.file)

    printed = set()

    absolute = f"file://{path.resolve().absolute()}"

    for _, s in import_statements_recursive(urlparse(absolute)):
        s = urlunparse(s)
        if s not in printed:
            print(hash_buffer(s.encode("utf-8")), s)
        printed.add(s)


def action_dependency_dag():
    """Draws a Directed Acyclic Graph of the dependency tree.

    This requires `Graphviz` to generate the tree image and `feh` to display it
    on the screen.

    """
    path = Path(ARGS.file).resolve()
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
        h = hash_buffer(n.encode("utf-8"))
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
        h_source = hash_buffer(source.encode("utf-8"))
        h_target = hash_buffer(target.encode("utf-8"))
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
    path = Path(ARGS.file).resolve()

    with (TEMPDIR / "main.js").open("w+") as main_file:
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
        url = str(imp).encode("utf-8")
        h = hash_buffer(url)
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

    if ARGS.output:
        output_path = Path(ARGS.output).resolve()
        output_path.write_text(output)
    else:
        print(output)


def action_nuke_cache():
    """Deletes the cached files."""

    print("Deleting cached files...")

    # Do not remove the cache directory itself, just its contents.
    for f in CACHE_DIR.iterdir():
        print(f"  {f}")
        f.unlink()
    print("Done.")

# Doctor checks


def doctor_check_java():
    try:
        subprocess.run(["java", "-version"], capture_output=True)
    except FileNotFoundError:
        return False
    return True


def doctor_check_curl():
    try:
        subprocess.run(["curl", "--version"], capture_output=True)
    except FileNotFoundError:
        return False
    return True


def doctor_check_graphviz():
    try:
        subprocess.run(["dot", "-V"], capture_output=True)
    except FileNotFoundError:
        return False
    return True


def doctor_check_feh():
    try:
        subprocess.run(["feh", "--version"], capture_output=True)
    except FileNotFoundError:
        return False
    return True


def doctor_check_closure_file():
    return CLOSURE.is_file()


def doctor_check_closure_version():
    try:
        proc = subprocess.run(
            [ARGS.java, "-jar", str(CLOSURE), "--version"],
            capture_output=True,
        )
        if proc.returncode != 0:
            return False
    except FileNotFoundError:
        return False
    return True


def action_doctor():
    """Checks if the environment is ready to run the tool."""
    print("Welcome to the doctor!")
    print("")
    print("This tool will check if your environment is ready to run the tool.")
    print("")
    print("If you are having problems, please run this tool with --verbose")
    print("and report the output to the issue tracker.")
    print("")

    for name in globals():
        if name.startswith("doctor_check_"):
            fn = globals()[name]
            pretty_name = name[13:].replace("_", " ").capitalize()
            print(f"Checking {pretty_name}...", end=" ")

            start_time = time.monotonic()
            try:
                result = fn()

                if result is None:
                    print("Unknown")
                elif result:
                    print("OK")
                else:
                    print("Failed")
            except Exception as e:
                if ARGS.verbose:
                    print("ERROR")
                    print(f"Exception: {e}")
                else:
                    print("ERROR (run with --verbose for more info)")
            end_time = time.monotonic()
            logging.debug(f"Check {name} took {end_time - start_time} seconds")


# Command-line arguments

parser = argparse.ArgumentParser()
parser.description = "Javascript builder and package manager"

# Parameters that are common to all commands
parser.add_argument("--verbose", action="store_true")
parser.add_argument(
    "--java",
    default="java",
    help="Path to the Java binary. Defaults to `java`.",
)

subparsers = parser.add_subparsers(dest="command", required=True)

# [action] ensure-closure
sp = subparsers.add_parser(
    "ensure-closure",
    help=action_ensure_closure.__doc__,
)
sp.set_defaults(func=action_ensure_closure)
sp.add_argument("--force", action="store_true")

# [action] list-deps
sp = subparsers.add_parser("list-deps", help=action_list_deps.__doc__)
sp.set_defaults(func=action_list_deps)
sp.add_argument("file", help="The file to list the dependencies of.")

# [action] dependency-dag
sp = subparsers.add_parser(
    "dependency-dag",
    help=action_dependency_dag.__doc__,
)
sp.set_defaults(func=action_dependency_dag)
sp.add_argument("file", help="The main file")

# [action] build
sp = subparsers.add_parser("build", help=action_build.__doc__)
sp.set_defaults(func=action_build)
sp.add_argument("file", help="The main file")
sp.add_argument("--output", help="The output file", nargs="?")
sp.add_argument(
    "--language_out", help="The language to use", default="ECMASCRIPT_2019"
)

# [action] nuke-cache
sp = subparsers.add_parser(
    "nuke-cache",
    help=action_nuke_cache.__doc__,
)
sp.set_defaults(func=action_nuke_cache)

# [action] doctor
sp = subparsers.add_parser("doctor", help=action_doctor.__doc__)
sp.set_defaults(func=action_doctor)

ARGS = parser.parse_args()

if ARGS.verbose:
    logging.getLogger().setLevel(logging.DEBUG)

logger.debug(f"Welcome to {NAME} v{VERSION}!")
logger.debug(f"Caching files in {CACHE_DIR}.")
logging.debug(f"Using temporary directory {TEMPDIR}")


def main():
    ARGS.func()


if __name__ == "__main__":
    main()
