#!/bin/sh
# GIT_ASKPASS helper for the clone init container. Prints the token straight
# from the mounted Secret to git's stdin pipe; it is never placed in an env var,
# a file on the shared volume, or the log. Only the init container mounts it.
case "$1" in
    Username*) printf '%s' "x-access-token" ;;
    *) node -e '
const fs = require("fs");
const auths = JSON.parse(fs.readFileSync("/secrets/git/.dockerconfigjson", "utf8")).auths;
const e = auths["ghcr.io"] || Object.values(auths)[0];
const pw = e.password || Buffer.from(e.auth, "base64").toString().split(":").slice(1).join(":");
process.stdout.write(pw);
' ;;
esac
