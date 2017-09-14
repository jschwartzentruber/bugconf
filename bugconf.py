#!/usr/bin/env python3
"Automate bug triage"

import argparse
import configparser
import glob
import json
import logging
import os
import re
import subprocess
import sys


import ffpuppet
import lithium


log = logging.getLogger("bugconf") # pylint: disable=invalid-name


def format_mdsw_backtrace(infile, threadno=None):
    """Format the output of `minidump_stackwalk -m` and return a list of frames from a single thread.

    @type infile: file-object
    @param infile: The input file to read minidump_stackwalk output from

    @type threadno: int or None
    @param threadno: Thread number to parse (None -> first encountered)
    """
    for line in infile:
        if threadno is None:
            parse_line = False
            if "|" in line:
                try:
                    threadno = int(line.split("|", 1)[0])
                    parse_line = True
                except ValueError:
                    pass
        else:
            parse_line = line.startswith("%d|" % threadno)
        if parse_line:
            # threadno, ...
            _, frame, lib, sym, src, line, addr = line.strip().split("|")
            if sym and src and line:
                # repo-type, repo, src, revision
                _, _, src, _ = src.split(":")
                yield "#%s: %s, at %s:%s" % (frame, sym, src, line)
            else:
                yield "#%s: %s+%s" % (frame, lib, addr)


class BugConf(object):
    "Class for automating bug triage"

    _CONFIGS = {"any_crash": (None, "Any crash is interesting during reduction", bool),
                #"asserts": ("s", "Detect soft assertions", bool),
                "build": ("b", "Folder name of downloaded build (relative to buildpath)", str),
                "buildpath": ("bp", "Path of downloaded builds", str),
                "char": ("c", "Use char reduction", bool),
                "extension": ("e", "Use DOMFuzz extension", bool),
                "extension_path": (None, "Path to DOMFuzz extension", str),
                "gdb": ("g", "Use GDB", bool),
                "js": ("j", "Use jsstr reduction", bool),
                "logfn": ("l", "Filename to save log to during repro", str),
                "memory": ("m", "Set memory limit", int),
                "min_crashes": ("n", "Require the testcase to crash n times before accepting the result.", int),
                "no_harness": (None, "Don't use a background tab to detect timeout", bool),
                "prefs": ("p", "Path to prefs.js to use", str),
                "reduce_file": ("rf", "Testcase to reduce", str),
                "reducer": (None, "Path to interesting.py", str),
                "repeat": (None, "Run intermittent testcase reduction multiple times", int),
                "safemode": (None, "Launch in Safe Mode (requires interaction)", bool),
                "sig": (None, "Specify signature to reduce", str),
                "skip": (None, "Skip n initial iterations", int),
                "strategy": (None, "Use lithium strategy", str),
                "symbol": (None, "Use symbol reduction", bool),
                "timeout": ("t", "Kill firefox if the testcase doesn't terminate within n seconds", int),
                "valgrind": (None, "Use Valgrind", bool),
                "xvfb": (None, "Use Xvfb", bool)}

    def __init__(self):
        "Initialize BugConf and load defaults if found"

        self.any_crash = None
        #self.asserts = None
        self._build = None
        self._buildpath = None
        self.char = None
        self.extension = None
        self._extension_path = None
        self.gdb = None
        self.js = None
        self._logfn = None
        self.memory = None
        self.min_crashes = None
        self.no_harness = None
        self._prefs = None
        self._reduce_file = None
        self._reducer = None
        self.repeat = None
        self.safemode = None
        self.sig = None
        self.skip = None
        self.strategy = None
        self.symbol = None
        self.timeout = None
        self.valgrind = None
        self.xvfb = None
        self._defaults = set()

        # load for defaults
        paths = [os.path.expanduser("~/.bugconfrc"),
                 os.path.expanduser("~/.config/bugconf/config")]
        for path in paths:
            try:
                with open(path) as cfgfp:
                    self.load(cfgfp, _defaults=True)
                    break
            except FileNotFoundError:
                pass

    @property
    def build(self):
        return self._build
    @build.setter
    def build(self, value):
        if value not in self.list_builds():
            raise Exception("Build not found")
        self._build = value

    @property
    def buildpath(self):
        return os.path.expanduser(self._buildpath)
    @buildpath.setter
    def buildpath(self, value):
        self._buildpath = value

    @property
    def extension_path(self):
        return os.path.expanduser(self._extension_path)
    @extension_path.setter
    def extension_path(self, value):
        self._extension_path = value

    @property
    def logfn(self):
        return os.path.expanduser(self._logfn)
    @logfn.setter
    def logfn(self, value):
        self._logfn = value

    @property
    def prefs(self):
        return os.path.expanduser(self._prefs)
    @prefs.setter
    def prefs(self, value):
        self._prefs = value

    @property
    def reducer(self):
        return os.path.expanduser(self._reducer)
    @reducer.setter
    def reducer(self, value):
        self._reducer = value

    @property
    def reduce_file(self):
        return self._reduce_file
    @reduce_file.setter
    def reduce_file(self, value):
        self._reduce_file = os.path.expanduser(value)

    def load(self, cfgfp, _defaults=False):
        "Set configs from the given file object"
        if _defaults:
            log.debug("loading defaults from %s", cfgfp.name)
        else:
            log.debug("loading from %s", cfgfp.name)
        obj = json.load(cfgfp)
        for cfg, value in obj.items():
            if cfg not in self._CONFIGS:
                raise Exception("Unsupported config: %s" % cfg)
            log.debug("setting %s to %r", cfg, value)
            setattr(self, cfg, value)
            if _defaults:
                self._defaults.add(cfg)
            else:
                self._defaults.discard(cfg)

    def dump(self, cfgfp):
        "Write configs which differ from global defaults to the given file object"
        obj = {}
        for cfg in self._CONFIGS:
            value = getattr(self, cfg)
            if value is None or cfg in self._defaults:
                continue
            obj[cfg] = value
        json.dump(obj, cfgfp, sort_keys=True, indent=1, separators=(',', ': '))

    def load_args(self, args):
        "Set configs from argparse Namespace"
        log.debug("loading from args")
        obj = vars(args)
        for cfg, value in obj.items():
            if cfg in self._CONFIGS and value is not None:
                log.debug("setting %s to %r", cfg, value)
                setattr(self, cfg, value)
                self._defaults.discard(cfg)

    def list_builds(self):
        "List builds available in the build path"
        for build in sorted(os.listdir(self.buildpath)):
            yield build

    def repro(self, testcase):
        "Run repro"
        # build ffpuppet command
        ffp = ffpuppet.FFPuppet(use_valgrind=self.valgrind, use_xvfb=self.xvfb, use_gdb=self.gdb)
        try:
            ffp.add_abort_token(re.compile(r"###!!!\s*\[Parent\].+?Error:\s*\(.+?PBrowser::Msg_Destroy\)"))
            kwds = {
                "prefs_js": self.prefs,
                "location": testcase
            }
            if self.safemode:
                kwds["safe_mode"] = True
            if self.extension:
                kwds["extension"] = self.extension_path
            if self.memory:
                kwds["memory_limit"] = self.memory * 1024 * 1024
            # run ffpuppet
            log.debug("launching ffpuppet")
            ffp.launch(os.path.join(self.buildpath, self.build, 'firefox'), **kwds)
            log.info("Running Firefox (pid: %d)...", ffp.get_pid())
            if ffp.wait(timeout=self.timeout) is None:
                log.info("Testcase hit %ds timeout", self.timeout)
        finally:
            log.info("Shutting down...")
            try:
                ffp.close()
                log.info("Firefox process closed")
                for path in glob.glob("log_*.txt"):
                    os.unlink(path)
                ffp.save_logs(".")
            finally:
                ffp.clean_up()
        # dump the logs
        stderr = None
        crashdata = None
        best_size = 0
        for log_fn in os.listdir("."):
            if log_fn.startswith("log_") and log_fn.endswith(".txt"):
                if "stderr" in log_fn:
                    stderr = log_fn
                elif "asan" in log_fn:
                    log_size = os.stat(log_fn).st_size
                    if log_size > best_size:
                        crashdata = log_fn
                        best_size = log_size
                elif "stdout" not in log_fn and crashdata is None:
                    # don't set best_size so that any asan log will replace this one
                    crashdata = log_fn
        if crashdata is None and stderr is not None:
            with open(stderr) as log_fp:
                sys.stdout.write(log_fp.read())
        elif crashdata is None:
            log.warning("No stderr!")
        else:
            # look for Assertion or panic in stderr
            if stderr is not None:
                with open(stderr) as log_fp:
                    for line in log_fp:
                        if "Assertion failure" in line:
                            sys.stdout.write(line)
                        elif "panicked at" in line:
                            sys.stdout.write(line)
            with open(crashdata) as log_fp:
                if "minidump" in crashdata:
                    sys.stdout.write("\n".join(format_mdsw_backtrace(log_fp)))
                else:
                    sys.stdout.write(log_fp.read())
        cfg = configparser.RawConfigParser()
        cfg.read(os.path.join(self.buildpath, self.build, 'firefox.fuzzmanagerconf'))
        product = '-'.join(part[0] for part in cfg['Main']['product'].split('-'))
        rev = cfg['Main']['product_version']
        log.warning('run in %s rev %s', product, rev)

    def reduce(self, testcase, verbose):
        "Run reduce"
        # build reduce command
        cmd = ["lithium"]
        if self.char:
            cmd.append("--char")
        if self.js:
            cmd.append("--js")
        if self.strategy is not None:
            cmd.extend(["--strategy", self.strategy])
        if self.symbol:
            cmd.append("--symbol")
        if self.reduce_file is not None:
            cmd.extend(["--testcase", self.reduce_file])
        cmd.append(self.reducer)
        cmd.extend(["-p", self.prefs, os.path.join(self.buildpath, self.build, 'firefox')])
        for arg in ["xvfb", "gdb", "valgrind"]:
            if getattr(self, arg):
                cmd.append("--%s" % arg)
        if self.any_crash:
            cmd.append("--any-crash")
        if self.min_crashes:
            cmd.extend(("--min-crashes", "%d" % self.min_crashes))
        if self.no_harness:
            cmd.append("--no-harness")
        if self.repeat:
            cmd.extend(("--repeat", "%d" % self.repeat))
        if self.sig:
            cmd.extend(("--sig", self.sig))
        if self.skip:
            cmd.extend(("--skip", "%d" % self.skip))
        if verbose:
            cmd.append("-v")
        cmd.append(testcase)
        # run reduce

        log.debug("calling: %r", cmd)
        subprocess.check_call(cmd)
        return

        lith = lithium.Lithium()
        lith.processArgs(cmd)

        try:
            return lith.run()

        except lithium.LithiumError as exc:
            log.error(exc)

    @classmethod
    def parse_args(cls, cmd):
        "Parse command line arguments"
        testcase = cmd in {"bcrepro", "bcreduce"}
        parser = argparse.ArgumentParser()
        for cfg, (short, help_, type_) in cls._CONFIGS.items():
            action = {str: "store",
                      int: "store",
                      bool: "store_true"}[type_]
            args = ["--%s" % cfg.replace("_", "-")]
            if short is not None:
                args.append("-%s" % short)
            kwds = {"action": action,
                    "default": None,
                    "help": help_}
            if type_ is not bool:
                kwds["type"] = type_
            parser.add_argument(*args, **kwds)
        if testcase:
            parser.add_argument("testcase", help="Testcase to operate on")
        parser.add_argument("--write", "-w", action="store_true", help="Write options to bugconf")
        parser.add_argument("--verbose", "-v", action="store_true", help="Be more verbose")
        return parser.parse_args()

    @classmethod
    def main(cls):
        "Main"
        if len(logging.getLogger().handlers) == 0:
            logging.basicConfig(level=logging.INFO)
        cmd = os.path.basename(sys.argv[0])
        args = cls.parse_args(cmd)
        if args.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        bcobj = cls()
        try:
            with open("bugconf") as cfgfp:
                bcobj.load(cfgfp)
        except FileNotFoundError:
            if cmd != "bclistbuilds":
                log.warning("No bugconf file found in current directory")
        bcobj.load_args(args)
        if cmd == "bcrepro":
            bcobj.repro(args.testcase)
        elif cmd == "bcreduce":
            bcobj.reduce(args.testcase, args.verbose)
        elif cmd == "bclistbuilds":
            for build in bcobj.list_builds():
                print(build)
        elif not args.write:
            log.warning("nothing to do!")
        if args.write:
            with open("bugconf", "w") as cfgfp:
                bcobj.dump(cfgfp)

if __name__ == "__main__":
    BugConf.main()
