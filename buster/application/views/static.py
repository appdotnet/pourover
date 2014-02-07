from flask import render_template, redirect

from application import app


@app.route('/', endpoint='index')
@app.route('/signup/', endpoint='signup')
@app.route('/login/', endpoint='login')
@app.route('/login/instagram/', endpoint='login_instagram')
@app.route('/logout/', endpoint='logout')
def index():
    return render_template('index.html')

index.login_required = False


@app.route('/feed/<feed_type>/<feed_id>/', endpoint='feed_point')
def feed_point(feed_type, feed_id=None):
    return render_template('index.html')

feed_point.login_required = False


@app.route('/alerts/<alert_id>/', endpoint='alerts_detail')
def alerts_detail(alert_id=None):
    return redirect('https://directory.app.net/alerts/manage/%s/' % alert_id)

alerts_detail.login_required = False
