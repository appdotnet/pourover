pour-over
=========

RSS publishing for App.net


## Running the tests

To run the tests your need to identify the path to your Google App Engine SDK.

If you have already exported GAE_PATH into your enviroment for deploying you can just run tests.sh, otherwise you can call runtests.py directly like so

```sh
./runtests.py  [Your Google App Engine SDK Path] ./buster/tests/
```

On osx your GAE path is usualy `/usr/local/google_appengine`