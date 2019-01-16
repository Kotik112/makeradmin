import flask_cors
from flask import Flask, jsonify
from flask.wrappers import Response as FlaskResponse
from sqlalchemy.exc import OperationalError

from core.auth import authenticate_request
from service.config import get_mysql_config
from service.db import create_mysql_engine, shutdown_session
from service.error import ApiError, error_handler_api, error_handler_db, error_handler_500, error_handler_404
from service.traffic_logger import traffic_logger_init, traffic_logger_commit
from services import services

app = Flask(__name__)

flask_cors.CORS(
    app,
    max_age='1728000',
    allow_headers=['Origin', 'Content-Type', 'Accept', 'Authorization', 'X-Request-With',
                   'Access-Control-Allow-Origin'],
)

for path, service in services:
    app.register_blueprint(service, url_prefix=path)


def before_request_functions():
    traffic_logger_init()
    authenticate_request()


def after_request_functions(response: FlaskResponse):
    traffic_logger_commit(response)
    return response


app.register_error_handler(OperationalError, error_handler_db)
app.register_error_handler(ApiError, error_handler_api)
app.register_error_handler(500, error_handler_500)
app.register_error_handler(404, error_handler_404)
app.teardown_appcontext(shutdown_session)
app.before_request(before_request_functions)
app.after_request(after_request_functions)

engine = create_mysql_engine(**get_mysql_config())


@app.route("/")
def index():
    return jsonify(dict(status="ok")), 200


# TODO Use Sentry?
