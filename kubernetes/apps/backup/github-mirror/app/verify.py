#!/usr/bin/env python3
"""Integrity + completeness check for the GitHub mirror (read-only on the mirror).

For every repository the API says the owner has (private and forks included):
  * the bare clone must exist under <out>/repositories/<name>/repository
  * `git fsck --connectivity-only` must pass (also on the wiki clone if present)
A repository the API lists with size 0 may legitimately have no clone (empty
repo); it is counted as empty, not as a failure. Repositories on disk that the
API no longer lists were deleted upstream: they are KEPT and only counted.

Writes Pushgateway text-format metrics to --metrics. The success timestamp is
only written when backup rc == 0 and no repository failed.
Exit 0 = all good, 1 = any failure.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request


def api_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "github-mirror-verify",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def list_repos(api, owner, token):
    repos = []
    page = 1
    while True:
        url = "%s/user/repos?per_page=100&affiliation=owner&page=%d" % (api, page)
        batch = api_get(url, token)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return [r for r in repos if r["owner"]["login"].lower() == owner.lower()]


def fsck(path):
    """Return None if healthy, else a short reason."""
    try:
        bare = subprocess.run(
            ["git", "-C", path, "rev-parse", "--is-bare-repository"],
            capture_output=True, text=True, timeout=120)
        if bare.stdout.strip() != "true":
            return "not a bare repository"
        res = subprocess.run(
            ["git", "-C", path, "fsck", "--connectivity-only"],
            capture_output=True, text=True, timeout=1800)
        if res.returncode != 0:
            tail = (res.stderr or res.stdout).strip().splitlines()[-1:]
            return "fsck failed: " + " ".join(tail)
    except subprocess.TimeoutExpired:
        return "git timed out"
    return None


CRED_URL = re.compile(r"://[^/@\s]+:[^@\s]+@")


def scrub_all(repos_dir):
    """Unconditional pass over EVERY clone on disk (also repos no longer in the
    API list), run before any API call so an API failure cannot leave a token
    in a config. Returns the list of clones whose config still holds one."""
    bad = []
    if not os.path.isdir(repos_dir):
        return bad
    for name in sorted(os.listdir(repos_dir)):
        for sub in ("repository", "wiki"):
            path = os.path.join(repos_dir, name, sub)
            cfg = os.path.join(path, "config")
            if not os.path.isfile(cfg):
                continue
            url = "https://github.com/OWNER/%s.git" % name
            if sub == "wiki":
                url = url.replace(".git", ".wiki.git")
            if scrub_remote(path, url):
                bad.append(name + "/" + sub)
    return bad


def scrub_remote(path, url):
    """python-github-backup stores the authenticated clone URL (with the PAT) as
    the remote. The mirror is itself backed up off-site, so rewrite it to the
    token-free URL and refuse to continue if a token is still in the config."""
    subprocess.run(["git", "-C", path, "remote", "set-url", "origin", url],
                   capture_output=True, text=True, timeout=60)
    cfg = os.path.join(path, "config")
    try:
        with open(cfg) as fh:
            text = fh.read()
        if CRED_URL.search(text) or "github_pat_" in text or "ghp_" in text:
            return "token still present in git config"
    except OSError as exc:
        return "cannot read git config: %s" % exc
    return None


def tree_bytes(root):
    total = 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.lstat(os.path.join(base, name)).st_size
            except OSError:
                pass
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--backup-rc", type=int, default=0)
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--api", default="https://api.github.com")
    ap.add_argument("--repos-json", help="test hook: read the repo list from this file")
    args = ap.parse_args()

    scrub_bad = scrub_all(os.path.join(args.out, "repositories"))
    for item in scrub_bad:
        print("FAILED: token still present in git config: %s" % item)

    token = ""
    if args.token_file and os.path.exists(args.token_file):
        token = open(args.token_file).read().strip()

    if args.repos_json:
        expected = json.load(open(args.repos_json))
    else:
        try:
            expected = list_repos(args.api, args.owner, token)
        except Exception as exc:  # fail loud: an unknown list is a failure
            print("FAILED: cannot list repositories from the API: %s" % exc)
            expected = None

    repos_dir = os.path.join(args.out, "repositories")
    on_disk = set(os.listdir(repos_dir)) if os.path.isdir(repos_dir) else set()
    ok = 0
    empty = 0
    failed = []

    if expected is None:
        failed.append("api-list")
        expected = []

    names = set()
    for repo in expected:
        name = repo["name"]
        names.add(name)
        clone = os.path.join(repos_dir, name, "repository")
        if not os.path.isdir(clone):
            if repo.get("size", 1) == 0:
                empty += 1
                print("empty repository without clone (allowed): %s" % name)
            else:
                failed.append(name)
                print("FAILED: %s: no bare clone found" % name)
            continue
        url = "https://github.com/%s/%s.git" % (repo["owner"]["login"], name)
        reason = scrub_remote(clone, url) or fsck(clone)
        wiki = os.path.join(repos_dir, name, "wiki")
        if reason is None and os.path.isdir(wiki):
            reason = scrub_remote(wiki, url.replace(".git", ".wiki.git")) or fsck(wiki)
            if reason:
                reason = "wiki " + reason
        if reason:
            failed.append(name)
            print("FAILED: %s: %s" % (name, reason))
        else:
            ok += 1

    retained = sorted(on_disk - names) if names else []
    if retained:
        print("retained (deleted or renamed upstream, kept): %d" % len(retained))

    expected_count = len(expected)
    if ok + empty + len(failed) != expected_count:
        print("FAILED: internal count mismatch")
        failed.append("count")
    print("repos api=%d ok=%d empty=%d failed=%d retained=%d" % (
        expected_count, ok, empty, len(failed), len(retained)))

    failed.extend(scrub_bad)
    success = args.backup_rc == 0 and not failed
    now = int(time.time())
    lines = [
        "# TYPE github_mirror_repos gauge",
        "github_mirror_repos %d" % ok,
        "# TYPE github_mirror_failed_repos gauge",
        "github_mirror_failed_repos %d" % (len(failed) + (1 if args.backup_rc else 0)),
        "# TYPE github_mirror_retained_repos gauge",
        "github_mirror_retained_repos %d" % len(retained),
        "# TYPE github_mirror_bytes gauge",
        "github_mirror_bytes %d" % tree_bytes(args.out),
        "# TYPE github_mirror_duration_seconds gauge",
        "github_mirror_duration_seconds %d" % (now - args.start),
    ]
    if success:
        lines += [
            "# TYPE github_mirror_last_success_timestamp_seconds gauge",
            "github_mirror_last_success_timestamp_seconds %d" % now,
        ]
    with open(args.metrics, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
