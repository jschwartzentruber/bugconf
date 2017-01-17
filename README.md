BugConf helps you triage bugs in fewer keystrokes by remembering details for you
and using them to launch the automation steps.

Currently it assumes a workflow like this:

1. create a signature in FuzzManager
2. create a local working folder
3. download the best testcase from FM to the working folder
4. make sure the testcase reproduces locally
5. reduce the testcase
6. log the bug in bugzilla
7. attach the testcase and log to bugzilla
8. link the bug with the FM signature
9. rename the local folder to the bug id for future reference

Steps 4-5 are currently supported with the bcrepro and bcreduce commands respectively.

Roadmap
=======
- steps 2,3,7,8 from the workflow above
- submitting the reduced testcase back to FM to log it from there
- download other testcases from the signature (in case the best doesn't reproduce)
- use git to auto-version work in progress (single testcase.html & log.txt which are versioned with
  automatic & accurate commit messages

Installation
============
- install grizzly and its dependencies
- install bugconf.py to your path (~/bin or /usr/local/bin)
- create symlinks in your path (for i in bcrepro bcreduce bclistbuilds; do ln -s bugconf.py $i; done)
- install shell autocompletion if desired

Setup
=====
Create a global bugconf config in either ~/.config/bugconf/config or ~/.bugconfrc. It should look something like this:

    {
        "prefs": "~/prefs.js",
        "buildpath": "~/builds",
        "puppet": "~/src/m/ffpuppet/ffpuppet.py",
        "reducer": "~/src/m/grizzly/reduce.py",
        "logfn": "log.txt"
    }

`bclistbuilds` will list the contents of your build directory, and also gets used for autocomplete of `-b` option on any script.
If you add -w to any command, a bugconf file will get written there and will reproduce the same options next time.

Example:

    $ bugconf.py -b m-c-1234567-asan-opt -w
    WARNING:bugconf:No bugconf file found in current directory
    $ cat bugconf
    {
      "build": "m-c-1234567-asan-opt",
      "xvfb": false
    }
    
    $ bcrepro testcase.html
    #... runs testcase with the build in bugconf and prefs from global bugconf config
    
    $ bcrepro -p some-other-prefs.js -b m-c-1234568-asan-opt testcase.html
    #... override prefs and build for just this run

