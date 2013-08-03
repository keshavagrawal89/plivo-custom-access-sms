from functools import wraps
from werkzeug import SharedDataMiddleware
from flask import Flask, Response, request, make_response, render_template,redirect
import smtplib
import email
from email.MIMEBase import MIMEBase
from email.parser import Parser
from email.MIMEImage import MIMEImage
from email.MIMEText import MIMEText
from email.MIMEAudio import MIMEAudio
import uuid
import mimetypes
import string
import plivo
import os.path
import os
from os.path import dirname, join as joinpath
import redis
import uuid, time

app = Flask(__name__)

#redis = redis.Redis('localhost')

redis_url = os.getenv('REDISTOGO_URL','redis://localhost:9640')
redis = redis.from_url(redis_url)

gl_pass_code = ""

auth_id = '<auth_id>'
auth_token = '<auth_token>'


cloud = plivo.RestAPI(auth_id = auth_id, auth_token = auth_token, url = 'https://api.plivo.com')


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    return username == 'admin' and password == 'password'

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
    'Could not verify your access level for that URL.\n'
    'You have to login with proper credentials', 401,
    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


@app.route('/',methods=['GET','POST'])
def get_home():
	response = make_response(render_template("sendsms.html"))
	response.headers['Content-type'] = 'text/html'
	return response

@app.route('/admin/',methods=['GET','POST'])
@requires_auth
def admin():
	global gl_pass_code
	pass_code = gl_pass_code

	db_pass_code = redis.hget('temp_pass_code', 'pass_code')
	db_time_left = redis.hget('temp_pass_code', 'time_left')
	db_time_set = redis.hget('temp_pass_code', 'time_set')

	print db_time_set
	time_left = "Not Yet Set"
	if db_pass_code and db_pass_code != "":
		pass_code = db_pass_code
		time_left = 1200 - int(time.time() - float(db_time_set))
		if int(time_left) <= 0:
			print time_left
			redis.hset('temp_pass_code','time_left','expired')
			time_left = "Expired!"

	response = make_response(render_template("sendsms_admin.html", pass_code = pass_code, time_left = time_left))
	response.headers['Content-type'] = 'text/html'
	return response

@app.route('/admin/gen_pass_code/', methods=['POST'])
def get_pass_code():
	gen_pass_code()
	db_time_left = redis.hget('temp_pass_code', 'time_left')
	if db_time_left == "1200.0":
		db_time_left = 1200

	response = make_response(render_template("sendsms_admin.html", pass_code = gl_pass_code, time_left = db_time_left))
	response.headers['Content-type'] = 'text/html'
	return response

def gen_pass_code():
	global gl_pass_code
	gl_pass_code = uuid.uuid4()

	redis.hset('temp_pass_code','pass_code',gl_pass_code)
	redis.hset('temp_pass_code','time_left','1200.0')
	redis.hset('temp_pass_code','time_set',time.time())

@app.route('/send-message/', methods=['POST'])
def send_message():
	db_pass_code = redis.hget('temp_pass_code', 'pass_code')
	db_time_left = redis.hget('temp_pass_code', 'time_left')

	ui_pass_code = request.form.get('ui_pass_code','')
	dst_num = request.form.get('dstNum','')
	msg_text = request.form.get('msgText','')

	if ui_pass_code and ui_pass_code == db_pass_code and db_time_left != "expired" and dst_num.isdigit():
		cloud.send_message({'src':'<put_your_plivo_num>','dst': dst_num,'text': msg_text})
		response = make_response(render_template("codeused.html"))
	else:
		err_list = []
		if not ui_pass_code or ui_pass_code == "":
			err_list.append("Pass code was not entered or has expired!")
		else:
			err_list.append("Some error happened! Please report to sales and try again!")

		response = make_response(render_template("error.html" , err_list = err_list))

	response.headers['Content-type'] = 'text/html'
	return response


@app.route('/send-bulk-message/', methods=['POST'])
def send_message():
	db_pass_code = redis.hget('temp_pass_code', 'pass_code')
	db_time_left = redis.hget('temp_pass_code', 'time_left')

	ui_pass_code = request.form.get('ui_pass_code','')
	dst_num = request.form.get('dstNum','')
	msg_text = request.form.get('msgText','')

	dst_num_list = dst_num.split(',')

	if ui_pass_code and ui_pass_code == db_pass_code and db_time_left != "expired":
		_dst = ""
		for num in dst_num_list:
			print num
			_dst = _dst + "<" + num
		_dst = _dst.lstrip('<')

		cloud.send_message({'src':'<put_your_plivo_num>','dst': _dst,'text': msg_text})
		response = make_response(render_template("codeused.html"))
	else:
		err_list = []
		if not ui_pass_code or ui_pass_code == "":
			err_list.append("Pass code was not entered")
		elif ui_pass_code != db_pass_code:
			err_list.append("Passcode has expired!")
		else:
			err_list.append("Some error happened! Please report to sales and try again!")

		response = make_response(render_template("error.html" , err_list = err_list))
	
	response.headers['Content-type'] = 'text/html'
	return response


if __name__ == '__main__':
	port = int(os.environ.get('PORT', 5555))
	app.run(host='0.0.0.0', port=port, debug=True)
