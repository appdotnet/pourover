#!/bin/bash -xe

root_dir="`dirname \"$0\"`"
cd "$root_dir/gob"
grunt build --force  # todo: remove --force
cd -

mkdir -p "$root_dir/buster/static" "$root_dir/buster/application/templates"
rsync -avz --delete "$root_dir/gob/dist/scripts" "$root_dir/gob/dist/styles" "$root_dir/buster/static/"
cp "$root_dir/gob/dist/"*.html "$root_dir/buster/application/templates"

cd "$root_dir"
python "$GAE_PATH/appcfg.py" update buster/ --oauth2 --noauth_local_webserver
cd -
