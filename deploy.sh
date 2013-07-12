#!/bin/bash -xe

root_dir="`dirname \"$0\"`"
cd "$root_dir/gob"
grunt build --force  # todo: remove --force
cd -
rsync -avz --delete "$root_dir/gob/dist/" "$root_dir/buster/static/"
cp "$root_dir/gob/dist/index.html" "$root_dir/gob/dist/404.html" "$root_dir/buster/application/templates/"
rm -f "$root_dir/buster/static/index.html" "$root_dir/buster/static/404.html"

cd "$root_dir"
python "$GAE_PATH/appcfg.py" update buster/ --oauth2 --noauth_local_webserver
cd -
