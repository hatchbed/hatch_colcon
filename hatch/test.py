import os
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from .common import (get_workspace_dir, get_package,
                     clr, _GREEN, _YELLOW, _RED, _BOLD_RED)

import hatch.common as _common


def register(subparsers):
    parser = subparsers.add_parser("test", help="Tests a colcon workspace.")
    parser.add_argument("--workspace", "-w", default=".",
                        help="The path to the colcon workspace (default: \".\")")
    packages_group = parser.add_argument_group('Packages', 'Select packages to test.')
    packages_group.add_argument(
        "pkgs", metavar="PKGNAME", nargs='*', type=str,
        help='Explicitly specify a list of specific packages to test.')
    packages_group.add_argument(
        "--this", action="store_true",
        help="Test the package containing the current working directory.")
    packages_group.add_argument(
        "--no-deps", action="store_true",
        help="Only test specified packages, not their dependencies.")
    config_group = parser.add_argument_group('Config', "Parameters for the underlying build system.")
    config_group.add_argument(
        "--colcon-build-args", metavar='ARG', dest='colcon_build_args',
        nargs="+", required=False, type=str, default=None,
        help="Additional arguments for colcon")
    config_group.add_argument("--verbose", "-v", action="store_true",
                              help="Show the status of every individual test case.")
    config_group.add_argument("--results-only", "-r", action="store_true",
                              help="Show results from the last test run without re-running.")
    config_group.add_argument("--no-color", action="store_true",
                              help="Disable colored output.")
    parser.set_defaults(func=test_command)


def get_xunit_path_from_cmdline(cmdline):
    """Extract the xunit result file path from a run_test.py FullCommandLine."""
    try:
        tokens = shlex.split(cmdline)
        for i, token in enumerate(tokens):
            if 'run_test.py' in token and i + 1 < len(tokens):
                return tokens[i + 1]
    except Exception:
        pass
    return None


def parse_xunit_results(xunit_path):
    """Parse a JUnit/xunit/GTest XML file.

    Returns (total, passed, skipped, failures, errors, failed_names, all_cases) or None on error.
    all_cases is a list of (name, status, detail) where status is 'passed', 'failed',
    'skipped', or 'error'.
    """
    try:
        tree = ET.parse(xunit_path)
        root = tree.getroot()
        total = failures = errors = skipped = 0
        failed_names = []
        all_cases = []

        suites = root.findall('testsuite') if root.tag == 'testsuites' else [root]
        for suite in suites:
            total += int(suite.get('tests', 0))
            failures += int(suite.get('failures', 0))
            errors += int(suite.get('errors', 0))
            skipped += int(suite.get('skipped', suite.get('disabled', 0)))
            for tc in suite.findall('testcase'):
                tc_name = tc.get('name', 'unknown')
                detail = None
                fail_el = tc.find('failure')
                err_el = tc.find('error')
                if fail_el is not None:
                    status = 'failed'
                    failed_names.append(tc_name)
                    detail = fail_el.get('message') or (fail_el.text or '').strip()
                elif err_el is not None:
                    status = 'error'
                    failed_names.append(tc_name)
                    detail = err_el.get('message') or (err_el.text or '').strip()
                elif tc.find('skipped') is not None or tc.get('status') == 'notrun':
                    status = 'skipped'
                else:
                    status = 'passed'
                all_cases.append((tc_name, status, detail))

        passed = total - failures - errors - skipped
        return total, passed, skipped, failures, errors, failed_names, all_cases
    except Exception:
        return None


def get_latest_ctest_xml(pkg_build_dir):
    """Return the path to the most recent Test.xml for a package, or None."""
    testing_dir = os.path.join(pkg_build_dir, 'Testing')
    if not os.path.isdir(testing_dir):
        return None
    timestamps = sorted([
        d for d in os.listdir(testing_dir)
        if os.path.isdir(os.path.join(testing_dir, d)) and d != 'Temporary'
    ])
    if not timestamps:
        return None
    xml_path = os.path.join(testing_dir, timestamps[-1], 'Test.xml')
    return xml_path if os.path.isfile(xml_path) else None


def print_test_results(workspace, build_space, verbose=False, packages=None):
    """Parse CTest XML files and print a nested test result summary.

    Returns 0 if all tests passed, 1 if any failed.
    If packages is provided, only results for those packages are shown.
    """
    build_dir = os.path.join(workspace, build_space)
    if not os.path.isdir(build_dir):
        print("No build directory found, no test results to show.")
        return 1

    all_pkgs = sorted([
        d for d in os.listdir(build_dir)
        if os.path.isdir(os.path.join(build_dir, d, 'Testing'))
    ])

    if packages:
        all_pkgs = [p for p in all_pkgs if p in packages]

    if not all_pkgs:
        print("No test results found.")
        return 0

    packages = all_pkgs

    total_suites = total_suites_passed = 0
    total_tests = total_passed = total_skipped = total_failed = 0
    any_failure = False

    print()
    print("-" * 70)

    for pkg in packages:
        ctest_xml = get_latest_ctest_xml(os.path.join(build_dir, pkg))
        if ctest_xml is None:
            continue
        try:
            root = ET.parse(ctest_xml).getroot()
        except Exception:
            continue

        test_entries = root.findall('.//Testing/Test')
        if not test_entries:
            continue

        suite_data = []
        pkg_tests = pkg_passed = pkg_skipped = pkg_failed_tests = pkg_suites_passed = 0
        pkg_failed = False

        for entry in test_entries:
            name = entry.findtext('Name', '')
            suite_ok = entry.get('Status') == 'passed'

            exec_time = None
            for nm in entry.findall('.//NamedMeasurement'):
                if nm.get('name') == 'Execution Time':
                    try:
                        exec_time = float(nm.findtext('Value', '0'))
                    except ValueError:
                        pass

            labels = [lbl.text for lbl in entry.findall('.//Label') if lbl.text]
            label = labels[0] if labels else ''

            xunit_path = get_xunit_path_from_cmdline(entry.findtext('FullCommandLine', ''))
            xunit = None
            if xunit_path and os.path.isfile(xunit_path):
                xunit = parse_xunit_results(xunit_path)

            if xunit:
                n_total, n_passed, n_skipped, n_failures, n_errors, _, _ = xunit
                pkg_tests += n_total
                pkg_passed += n_passed
                pkg_skipped += n_skipped
                pkg_failed_tests += n_failures + n_errors
                if n_failures or n_errors:
                    suite_ok = False

            if suite_ok:
                pkg_suites_passed += 1
            else:
                pkg_failed = True

            suite_data.append((name, label, exec_time, xunit, suite_ok))

        if pkg_failed:
            any_failure = True
        n_suites = len(test_entries)
        total_suites += n_suites
        total_suites_passed += pkg_suites_passed
        total_tests += pkg_tests
        total_passed += pkg_passed
        total_skipped += pkg_skipped
        total_failed += pkg_failed_tests

        if pkg_tests > 0:
            parts = [clr(f"{pkg_passed} passed", _GREEN)]
            if pkg_skipped:
                parts.append(clr(f"{pkg_skipped} skipped", _YELLOW))
            if pkg_failed_tests:
                parts.append(clr(f"{pkg_failed_tests} failed", _BOLD_RED))
            print(f"{pkg}: {pkg_suites_passed}/{n_suites} suites passed  ({', '.join(parts)})")
        else:
            print(f"{pkg}: {pkg_suites_passed}/{n_suites} suites passed")

        name_w = max(len(s[0]) for s in suite_data)
        label_w = max((len(f" [{s[1]}]") if s[1] else 0) for s in suite_data)

        suite_counts = []
        for name, label, exec_time, xunit, suite_ok in suite_data:
            if xunit:
                n_total, n_passed, n_skipped, n_failures, n_errors, failed_names, all_cases = xunit
                plain_parts = []
                counts = []
                if n_passed:
                    plain_parts.append(f"{n_passed} passed")
                    counts.append(clr(f"{n_passed} passed", _GREEN))
                if n_skipped:
                    plain_parts.append(f"{n_skipped} skipped")
                    counts.append(clr(f"{n_skipped} skipped", _YELLOW))
                if n_failures:
                    plain_parts.append(f"{n_failures} failed")
                    counts.append(clr(f"{n_failures} failed", _BOLD_RED))
                if n_errors:
                    plain_parts.append(f"{n_errors} errors")
                    counts.append(clr(f"{n_errors} errors", _BOLD_RED))
                counts_str = ", ".join(counts) if counts else "0 tests"
                counts_vis = len(", ".join(plain_parts)) if plain_parts else len("0 tests")
            else:
                counts_str = clr("passed", _GREEN) if suite_ok else clr("FAILED", _BOLD_RED)
                counts_vis = len("passed" if suite_ok else "FAILED")
            suite_counts.append((xunit, counts_str, counts_vis))

        counts_w = max(cv for _, _, cv in suite_counts)

        for (name, label, exec_time, xunit, suite_ok), (xunit2, counts_str, counts_vis) in \
                zip(suite_data, suite_counts):
            tag = clr("[ ok ]", _GREEN) if suite_ok else clr("[FAIL]", _BOLD_RED)
            label_str = f" [{label}]" if label else ""
            time_str = f"  ({exec_time:.2f}s)" if exec_time is not None else ""
            padding = " " * (counts_w - counts_vis)

            if xunit:
                n_total, n_passed, n_skipped, n_failures, n_errors, failed_names, all_cases = xunit
                print(f"  {tag} {name:<{name_w}}{label_str:<{label_w}}  "
                      f"{counts_str}{padding}{time_str}")
                if verbose:
                    for tc_name, tc_status, detail in all_cases:
                        tc_tag = clr("[ ok ]", _GREEN) if tc_status == 'passed' else \
                                 clr("[SKIP]", _YELLOW) if tc_status == 'skipped' else \
                                 clr("[FAIL]", _BOLD_RED)
                        print(f"       {tc_tag} {tc_name}")
                        if detail and tc_status in ('failed', 'error'):
                            for line in detail.splitlines():
                                print(f"              {clr(line, _RED)}")
                elif failed_names:
                    for tc_name, tc_status, detail in all_cases:
                        if tc_status not in ('failed', 'error'):
                            continue
                        print(f"         FAILED: {tc_name}")
                        if detail:
                            for line in detail.splitlines():
                                print(f"                {clr(line, _RED)}")
            else:
                print(f"  {tag} {name:<{name_w}}{label_str:<{label_w}}  "
                      f"{counts_str}{padding}{time_str}")

        print()

    print("-" * 70)
    suite_str = f"{total_suites_passed}/{total_suites} suites"
    summary_status = clr("FAILED", _BOLD_RED) if any_failure else clr("passed", _GREEN)
    if total_tests > 0:
        test_parts = [clr(f"{total_passed} passed", _GREEN)]
        if total_skipped:
            test_parts.append(clr(f"{total_skipped} skipped", _YELLOW))
        if total_failed:
            test_parts.append(clr(f"{total_failed} failed", _BOLD_RED))
        print(f"Summary: {suite_str} | {', '.join(test_parts)} -- {summary_status}")
    else:
        print(f"Summary: {suite_str} -- {summary_status}")
    print("-" * 70)

    return 1 if any_failure else 0


def test_command(args):
    if args.no_color:
        _common._color = False

    workspace = os.path.abspath(args.workspace)

    if not os.path.exists(workspace):
        print(f"Error: The specified workspace directory '{workspace}' does not exist.")
        sys.exit(1)

    workspace = get_workspace_dir(workspace)
    if workspace is None:
        print(f"Error: Parent colcon workspace directory does not exist.")
        sys.exit(1)

    config_file = os.path.join(workspace, ".hatch", "config.yaml")

    if not os.path.exists(config_file):
        print(f"Error: Workspace has not been initialized. Run 'hatch init' first.")
        sys.exit(1)

    import yaml
    config_content = {
        "build_space": "build",
        "colcon_build_args": [],
        "nice": 0,
        "extend_path": "",
        "install_space": "install",
        "test_result_space": "test_results"
    }
    with open(config_file, "r") as f:
        config_content.update(yaml.safe_load(f))

    build_space = config_content.get("build_space", "build") or "build"

    if args.results_only:
        packages = args.pkgs
        if args.this:
            current_package = get_package(args.workspace)
            if current_package:
                packages.append(current_package)
        result_code = print_test_results(
            workspace, build_space, verbose=args.verbose,
            packages=packages if packages else None)
        sys.exit(result_code)

    colcon_cmd = ["colcon", "test"]
    colcon_cmd += ['--build-base', build_space]

    test_result_space = config_content.get("test_result_space", "test_results") or "test_results"
    colcon_cmd += ['--test-result-base', test_result_space]

    if args.colcon_build_args:
        colcon_cmd += args.colcon_build_args

    nice = config_content.get("nice", 0) or 0

    packages = args.pkgs
    if args.this:
        current_package = get_package(args.workspace)
        if current_package:
            packages.append(current_package)

    if packages:
        if args.no_deps:
            colcon_cmd += ['--packages-select'] + packages
        else:
            colcon_cmd += ['--packages-up-to'] + packages

    colcon_shell_cmd = ' '.join(colcon_cmd)

    extend_path = config_content.get("extend_path", None)
    if extend_path:
        extend_script = os.path.join(extend_path, "setup.bash")
        if not os.path.exists(extend_script):
            print(f"Error: '{extend_script}' does not exist.")
            sys.exit(1)
        colcon_shell_cmd = f'source {extend_script} && ' + colcon_shell_cmd

    print(f"Running: {colcon_shell_cmd}")

    process = subprocess.Popen(
        colcon_shell_cmd,
        cwd=workspace,
        shell=True,
        executable="/bin/bash",
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    while process.poll() is None:
        subprocess.run(
            f"renice -n {nice} -p $(pgrep -g $(ps -o pgid= -p {process.pid}))",
            shell=True,
            executable="/bin/bash",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        time.sleep(1)

    test_returncode = process.returncode

    result_code = print_test_results(
        workspace, build_space, verbose=args.verbose,
        packages=packages if packages else None)
    sys.exit(max(test_returncode, result_code))
