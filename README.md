PourOver
=========

RSS publishing for App.net.

## Architecture

PourOver is partitioned into two major parts. The first part, Buster, is an API layer. It handles authentication, data storage, and validation. It runs on top of Google AppEngine. We are using Flask as the main back-end framework.

The second part of PourOver is Gob. It is a mostly static client-side app that interacts with the API provided by Buster. We are using [Yeoman](http://yeoman.io/) to build the front-end app that powers the user interface. We are using Angular.js as the main front-end framework.

## Getting Started

There are a couple of pre-requisites for getting PourOver up and running.

Most of the build commands assume you're in the root of the PourOver checkout.

* **An App.net developer account** - You will need an App.net developer account.
* **Google App Engine** - This project runs on [Google AppEngine](https://developers.google.com/appengine/), so you will need the [Python SDK](https://developers.google.com/appengine/downloads#Google_App_Engine_SDK_for_Python) installed.
* **Node.js, npm, and Grunt** - You will need Node.js, npm, and Grunt installed for the build process to work. If you don't already have Node.js and npm installed you can follow this guide from Joyent [Installing Node and npm](http://www.joyent.com/blog/installing-node-and-npm). You'll also need [Grunt](http://gruntjs.com/), a Javascript build tool that's similar to rake. To install it, follow this [getting started guide](http://gruntjs.com/getting-started).
* **Compass** - We are also using [Compass](http://compass-style.org/) to compile sass to css. To install Compass, follow the [Compass install guide](http://compass-style.org/install/).

### Create an App.net App

Create an App.net app by going to https://account.app.net/developer/apps/ and clicking "Create An App." Make sure to add http://localhost:9000 as a redirect URI. Be sure to note your Client ID -- you'll need it in a second.

### Setup up the API layer

First thing you need to do is generate your secret keys. You can do this by running the following command.

```sh
python ./buster/application/generate_keys.py
```

It should generate the file `./buster/application/secret_keys.py`.

Next you will need to change two variables in `./buster/application/settings.py`. Make sure to change `CLIENT_ID` to  the Client ID of your app, and the `ADMIN_EMAIL` to your email address. Any uncaught exceptions will be sent to that email.

Once you have completed those changes, you should be able to start up the application by running:

```sh
dev_appserver.py buster/
```

The API should now be up and running at http://localhost:8080. Next, you'll set up the client-side UI, which runs as a separate server process while you're developing it, in order to take advantage of good stuff like live reloads, etc.

### Setup the client-side app

The first step here is to get your note environment up and running. You'll want to leave the API process running in the background and probably run these commands in a separate shell window.

You will need to edit `gob/app/scripts/controllers/main.js`. Make sure that you update `$scope.client_id` to your client ID.

Once you have modified main.js, we can install all the dependencies. Run these commands:

```sh
cd gob
npm install    # install the node dependencies
bower install  # install the client-side dependencies
grunt server   # Should start a development server at http://localhost:9000
```

Now visit http://localhost:9000 and you should see the splash screen.

### Off and running

The development server (on localhost:9000) is set up to proxy all /api calls to localhost:8080. You'll still need to run both server processes while developing, but your browser won't hit the API server directly.

From here you can modify the application files, and you should see your changes reflected in your browser.

## Deploying to App Engine

First, create an AppEngine application.

Be sure to change the key `application` in `buster/app.yaml` to reflect the slug of your AppEngine instance.

Then run `./deploy.sh`

## Running the tests

To run the tests, you'll need to identify the path to your Google App Engine SDK.

If you have already exported `GAE_PATH` into your environment for deploying, you can just run `./tests.sh`; otherwise, you can call runtests.py directly like so:

```sh
./runtests.py  [Your Google App Engine SDK Path] ./buster/tests/
```

On OS X, your GAE path is usually `/usr/local/google_appengine`
