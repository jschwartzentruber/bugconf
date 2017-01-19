#!/usr/bin/env python3
"Automate bug triage"

import argparse
import json
import logging
import os
import subprocess
import sys


log = logging.getLogger("bugconf") # pylint: disable=invalid-name


class BugConf(object):
    "Class for automating bug triage"

    _CONFIGS = {"build": ("b", "Folder name of downloaded build (relative to buildpath)", str),
                "buildpath": ("bp", "Path of downloaded builds", str),
                "logfn": ("l", "Filename to save log to during repro", str),
                "prefs": ("p", "Path to prefs.js to use", str),
                "puppet": (None, "Path to ffpuppet.py", str),
                "reducer": (None, "Path to reduce.py", str),
                "gdb": ("g", "Use GDB", bool),
                "valgrind": (None, "Use Valgrind", bool),
                "windbg": (None, "Use WinDBG", bool),
                "asserts": ("s", "Detect soft assertions", bool),
                "extension": ("e", "Use DOMFuzz extension", bool),
                "memory": ("m", "Set memory limit", int),
                "n_tries": (None, "Require N crashes for each reduction", int),
                "skip": (None, "Skip N initial tries during reduction", int),
                "reducers": ("r", "Specify reduce strategies", str),
                "extension_path": (None, "Path to DOMFuzz extension", str),
                "xvfb": (None, "Use Xvfb", bool)}

    def __init__(self):
        "Initialize BugConf and load defaults if found"

        self._build = None
        self._buildpath = None
        self._logfn = None
        self._prefs = None
        self._puppet = None
        self._reducer = None
        self.gdb = None
        self.valgrind = None
        self.windbg = None
        self.asserts = None
        self.extension = None
        self.memory = None
        self.n_tries = None
        self.skip = None
        self.reducers = None
        self._extension_path = None
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
    def puppet(self):
        return os.path.expanduser(self._puppet)
    @puppet.setter
    def puppet(self, value):
        self._puppet = value

    @property
    def reducer(self):
        return os.path.expanduser(self._reducer)
    @reducer.setter
    def reducer(self, value):
        self._reducer = value

    @property
    def extension_path(self):
        return os.path.expanduser(self._extension_path)
    @extension_path.setter
    def extension_path(self, value):
        self._extension_path = value

    def load(self, cfgfp, _defaults=False):
        "Set configs from the given file object"
        if _defaults:
            log.info("loading defaults from %s", cfgfp.name)
        else:
            log.info("loading from %s", cfgfp.name)
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
        log.info("loading from args")
        obj = vars(args)
        for cfg, value in obj.items():
            if cfg in self._CONFIGS and value is not None:
                log.debug("setting %s to %r", cfg, value)
                setattr(self, cfg, value)
                self._defaults.discard(cfg)

    def list_builds(self):
        "List builds available in the build path"
        for build in os.listdir(self.buildpath):
            yield build

    def repro(self, testcase, verbose=0):
        "Run repro"
        # build ffpuppet command
        cmd = [self.puppet, "-p", self.prefs, os.path.join(self.buildpath, self.build, 'firefox'), "-u", testcase]
        cmd.extend(["-v"] * verbose)
        for arg in ("xvfb", "gdb", "valgrind", "windbg"):
            if getattr(self, arg):
                cmd.append("--%s" % arg)
        for arg in ("memory", "extension", "logfn"):
            if getattr(self, arg):
                cmd.append("--%s" % ("log" if arg == "logfn" else arg))
                if arg == "extension":
                    cmd.append(self.extension_path)
                else:
                    cmd.append(str(getattr(self, arg)))
        # run ffpuppet
        log.debug("calling: %r", cmd)
        subprocess.check_call(cmd)
        if self.logfn:
            # cat the log
            with open(self.logfn) as logfp:
                sys.stdout.write(logfp.read())

    def reduce(self, testcase, verbose=0):
        "Run reduce"
        # build reduce command
        cmd = [self.reducer, "-p", self.prefs, os.path.join(self.buildpath, self.build, 'firefox'), testcase]
        cmd.extend(["-v"] * verbose)
        for arg in ("xvfb", "asserts", "gdb", "valgrind", "windbg"):
            if getattr(self, arg):
                cmd.append("--%s" % arg)
        for arg in ("reducers", "skip", "n_tries", "memory", "extension"):
            if getattr(self, arg):
                cmd.append("--%s" % ("reducer" if arg == "reducers" else arg.replace("_", "-")))
                if arg == "extension":
                    cmd.append(self.extension_path)
                else:
                    cmd.append(str(getattr(self, arg)))
        # run reduce
        log.debug("calling: %r", cmd)
        subprocess.check_call(cmd)

    @classmethod
    def parse_args(cls, cmd):
        "Parse command line arguments"
        testcase = cmd in {"bcrepro", "bcreduce"}
        parser = argparse.ArgumentParser()
        for cfg, (short, help_, type_) in cls._CONFIGS.items():
            action = {str: "store",
                      int: "store",
                      bool: "store_true"}[type_]
            args = ["--%s" % cfg]
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
        parser.add_argument("--verbose", "-v", action="count", default=0, help="Be more verbose")
        return parser.parse_args()

    @classmethod
    def main(cls):
        "Main"
        if len(logging.getLogger().handlers) == 0:
            logging.basicConfig()
        cmd = os.path.basename(sys.argv[0])
        args = cls.parse_args(cmd)
        if args.verbose:
            logging.getLogger().setLevel(logging.INFO if args.verbose == 1 else logging.DEBUG)
        bcobj = cls()
        try:
            with open("bugconf") as cfgfp:
                bcobj.load(cfgfp)
        except FileNotFoundError:
            if cmd != "bclistbuilds":
                log.warning("No bugconf file found in current directory")
        bcobj.load_args(args)
        if cmd == "bcrepro":
            bcobj.repro(args.testcase, args.verbose)
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
