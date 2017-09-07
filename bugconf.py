#!/usr/bin/env python3
"Automate bug triage"

import argparse
import configparser
import json
import logging
import os
import subprocess
import sys


log = logging.getLogger("bugconf") # pylint: disable=invalid-name


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
                "no_harness": (None, "Don't use a background tab to detect timeout", bool),
                "prefs": ("p", "Path to prefs.js to use", str),
                "reduce_file": ("rf", "Testcase to reduce", str),
                "reducer": (None, "Path to interesting.py", str),
                "repeat": (None, "Run intermittent testcase reduction multiple times", int),
                "safemode": (None, "Launch in Safe Mode (requires interaction)", bool),
                "skip": (None, "Skip n initial iterations", int),
                "strategy": (None, "Use lithium strategy", str),
                "symbol": (None, "Use symbol reduction", bool),
                "valgrind": (None, "Use Valgrind", bool),
                "windbg": (None, "Use WinDBG", bool),
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
        self.no_harness = None
        self._prefs = None
        self._reduce_file = None
        self._reducer = None
        self.repeat = None
        self.safemode = None
        self.skip = None
        self.strategy = None
        self.symbol = None
        self.valgrind = None
        self.windbg = None
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
        for build in sorted(os.listdir(self.buildpath)):
            yield build

    def _add_ffpuppet_args(self, cmd, verbose=0):
        cmd.extend(["-p", self.prefs, os.path.join(self.buildpath, self.build, 'firefox')])
        cmd.extend(["-v"] * verbose)
        for arg in ["xvfb", "gdb", "valgrind", "windbg"]:
            if getattr(self, arg):
                cmd.append("--%s" % arg)
        if self.safemode:
            cmd.append("--safe-mode")
        if self.extension:
            cmd.extend(["--extension", self.extension_path])
        if self.memory:
            cmd.extend(["--memory", str(self.memory)])

    def repro(self, testcase, verbose=0):
        "Run repro"
        # build ffpuppet command
        cmd = ["python2", "-m", "ffpuppet", "-u", testcase]
        self._add_ffpuppet_args(cmd, verbose)
        cmd.extend(["--abort-token", r",name=PBrowser::Msg_Destroy)"])
        if self.logfn:
            cmd.extend(["--log", str(self.logfn)])
        # run ffpuppet
        log.debug("calling: %r", cmd)
        subprocess.check_call(cmd)
        if self.logfn:
            # cat the log
            with open(self.logfn) as logfp:
                sys.stdout.write(logfp.read())

        cfg = configparser.RawConfigParser()
        cfg.read(os.path.join(self.buildpath, self.build, 'firefox.fuzzmanagerconf'))
        product = '-'.join(part[0] for part in cfg['Main']['product'].split('-'))
        rev = cfg['Main']['product_version']
        log.warning('reproduced in %s rev %s', product, rev)

    def reduce(self, testcase, verbose=0):
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
        self._add_ffpuppet_args(cmd, verbose)
        if self.any_crash:
            cmd.append("--any-crash")
        if self.no_harness:
            cmd.append("--no-harness")
        if self.repeat:
            cmd.extend(("--repeat", "%d" % self.repeat))
        if self.skip:
            cmd.extend(("--skip", "%d" % self.skip))
        cmd.append(testcase)
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
