#!/usr/bin/env python
import argparse
import codecs
import configparser
import json
import os
import sys
import urllib.request


def _get_json(url):
    reader = codecs.getreader("utf-8")
    return json.load(reader(urllib.request.urlopen(url)))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("crash_id", type=int)
    return parser.parse_args()


def load_config():
    # load config
    config = configparser.RawConfigParser()
    config.read(os.path.expanduser(os.path.join("~", ".fuzzmanagerconf")))

    server_url = "%s://%s:%s" % (config.get("Main", "serverproto"),
                                 config.get("Main", "serverhost"),
                                 config.get("Main", "serverport"))
    try:
        auth_token = config.get("Main", "serverauthtoken")
    except configparser.NoOptionError:
        with open(config.get("Main", "serverauthtokenfile")) as auth_fp:
            auth_token = auth_fp.read().strip()
    return server_url, auth_token


def get_crash(server_url, auth_token, crash_id):
    req = urllib.request.Request("%s/crashmanager/rest/crashes/%s/" % (server_url, crash_id),
                                 headers={"Authorization": "Token %s" % auth_token})
    return _get_json(req)


def download_test(server_url, auth_token, crash):
    testcase_url = "%s/crashmanager/%s" % (server_url, crash["testcase"])
    auth_handler = urllib.request.HTTPBasicAuthHandler(urllib.request.HTTPPasswordMgrWithPriorAuth())
    auth_handler.add_password(None, testcase_url, "fuzzmanager", auth_token)
    opener = urllib.request.build_opener(auth_handler)
    testcase_data = opener.open(testcase_url).read()

    test_fn = os.path.basename(crash["testcase"])
    with open(test_fn, "wb") as test_fp:
        test_fp.write(testcase_data)
    return test_fn


def main():
    args = parse_args()
    server_url, auth_token = load_config()
    crash = get_crash(server_url, auth_token, args.crash_id)
    print("product=%s" % crash["product"], file=sys.stderr)
    print("product_version=%s" % crash["product_version"], file=sys.stderr)
    test_fn = download_test(server_url, auth_token, crash)
    print(test_fn)

if __name__ == "__main__":
    main()
