#!/usr/bin/env python3
import argparse
import codecs
import configparser
import json
import os
import re
import shutil
import sys
import urllib.request


def _get_json(url):
    reader = codecs.getreader("utf-8")
    return json.load(reader(urllib.request.urlopen(url)))


def parse_args_init_bug():
    parser = argparse.ArgumentParser()
    parser.add_argument("bucket_id", metavar="ID", type=int, help="FuzzManager signature ID")
    return parser.parse_args()


def parse_args_dl_crash():
    parser = argparse.ArgumentParser()
    parser.add_argument("crash_ids", metavar="ID", type=int, nargs="+", help="FuzzManager crash ID")
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
    req = urllib.request.Request("%s/crashmanager/rest/crashes/%d/" % (server_url, crash_id),
                                 headers={"Authorization": "Token %s" % auth_token})
    result = _get_json(req)
    result["id"] = crash_id
    return result


def init_bug(server_url, auth_token, bucket_id):
    # get bucket
    req = urllib.request.Request("%s/crashmanager/rest/buckets/%d/" % (server_url, bucket_id),
                                 headers={"Authorization": "Token %s" % auth_token})
    bucket = _get_json(req)
    # create directory
    dest = str(bucket_id) + " - " + re.sub(r", (at )?[^/]*(/[^/]+)+:\d+", "", bucket["shortDescription"])
    os.mkdir(dest)
    os.chdir(dest)
    print("creating " + dest, file=sys.stderr)
    with open("sig.json", "w") as sigfp:
        sigfp.write(bucket["signature"])
    # download a testcase
    query = {"op": "AND",
             "testcase__quality": bucket["best_quality"],
             "bucket": bucket_id}
    query_str = urllib.parse.urlencode({"query": json.dumps(query)})
    req = urllib.request.Request("%s/crashmanager/rest/crashes/?%s" % (server_url, query_str),
                                 headers={"Authorization": "Token %s" % auth_token})
    crash_list = _get_json(req)
    if not crash_list["count"]:
        raise Exception("Bucket %d has 0 crashes with quality=%d?" % (bucket_id, bucket["best_quality"]))
    return crash_list["results"][0]


def download_test(server_url, auth_token, crash):
    testcase_url = "%s/crashmanager/%s" % (server_url, crash["testcase"])
    auth_handler = urllib.request.HTTPBasicAuthHandler(urllib.request.HTTPPasswordMgrWithPriorAuth())
    auth_handler.add_password(None, testcase_url, "fuzzmanager", auth_token)
    opener = urllib.request.build_opener(auth_handler)
    testcase_fp = opener.open(testcase_url)

    test_fn = "%d%s" % (crash["id"], os.path.splitext(crash["testcase"])[1])
    with open(test_fn, "wb") as test_fp:
        shutil.copyfileobj(testcase_fp, test_fp)
    return test_fn


def dl_crash_main():
    args = parse_args_dl_crash()
    server_url, auth_token = load_config()
    for crash_id in args.crash_ids:
        crash = get_crash(server_url, auth_token, crash_id)
        print("product=%s" % crash["product"], file=sys.stderr)
        if "product_version" in crash:
            print("product_version=%s" % crash["product_version"], file=sys.stderr)
        test_fn = download_test(server_url, auth_token, crash)
        print(test_fn)


def init_bug_main():
    args = parse_args_init_bug()
    server_url, auth_token = load_config()
    crash = init_bug(server_url, auth_token, args.bucket_id)
    print("product=%s" % crash["product"], file=sys.stderr)
    print("product_version=%s" % crash["product_version"], file=sys.stderr)
    test_fn = download_test(server_url, auth_token, crash)
    print(test_fn)


if __name__ == "__main__":
    cmd = os.path.basename(sys.argv[0])
    if cmd == "dlcrash":
        dl_crash_main()
    elif cmd == "initbug":
        init_bug_main()
