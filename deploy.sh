#!/bin/bash

root_dir="`dirname \"$0\"`"
cd "$root_dir/gob"
grunt build --force  # todo: remove --force
cd -
rsync -avz --delete "$root_dir/gob/dist" "$root_dir/buster/static"

cd "$root_dir"
python "$GAE_PATH/appcfg.py" update buster/ --oauth2 --noauth_local_webserver
cd -
