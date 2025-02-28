# -*- coding: utf-8 -*-
import os
try:
    from urllib.parse import unquote
except ImportError:
    from urllib2 import unquote

from pprint import pprint as pp

import coloredlogs
import logging
from flask import current_app, Flask, redirect, request, url_for
from flask_babel import Babel
from flask_login import current_user
from flaskext.markdown import Markdown
from scout.utils.matchmaker import mme_nodes

logger = logging.getLogger(__name__)

try:
    from chanjo_report.server.app import configure_template_filters
    from chanjo_report.server.blueprints import report_bp
    from chanjo_report.server.extensions import api as chanjo_api
except ImportError:
    chanjo_api = None
    report_bp = None
    configure_template_filters = None
    logger.info('chanjo report not installed!')

from . import extensions
from .blueprints import (alignviewers, public, genes, cases, login, variants, panels, dashboard,
                         api, phenotypes, institutes)


def create_app(config_file=None, config=None):
    """Flask app factory function."""
    app = Flask(__name__)
    app.config.from_pyfile('config.py')
    app.jinja_env.add_extension('jinja2.ext.do')
    if config:
        app.config.update(config)
    if config_file:
        app.config.from_pyfile(config_file)

    # If there is a MatchMaker Exchange server
    # collect the connected external nodes
    app.mme_nodes = mme_nodes(app.config.get('MME_URL'), app.config.get('MME_TOKEN'))


    app.config["JSON_SORT_KEYS"] = False
    current_log_level = logger.getEffectiveLevel()
    coloredlogs.install(level='DEBUG' if app.debug else current_log_level)
    configure_extensions(app)
    register_blueprints(app)
    register_filters(app)

    if not (app.debug or app.testing) and app.config.get('MAIL_USERNAME'):
        # setup email logging of errors
        configure_email_logging(app)

    @app.before_request
    def check_user():
        if not app.config.get('LOGIN_DISABLED') and request.endpoint:
            # check if the endpoint requires authentication
            static_endpoint = 'static' in request.endpoint or 'report' in request.endpoint
            public_endpoint = getattr(app.view_functions[request.endpoint],
                                      'is_public', False)
            relevant_endpoint = not (static_endpoint or public_endpoint)
            # if endpoint requires auth, check if user is authenticated
            if relevant_endpoint and not current_user.is_authenticated:
                # combine visited URL (convert byte string query string to unicode!)
                next_url = "{}?{}".format(request.path, request.query_string.decode())
                login_url = url_for('login.login', next=next_url)
                return redirect(login_url)

    return app


def configure_extensions(app):
    """Configure Flask extensions."""
    extensions.toolbar.init_app(app)
    extensions.bootstrap.init_app(app)
    extensions.mongo.init_app(app)
    extensions.store.init_app(app)
    extensions.login_manager.init_app(app)
    extensions.oauth.init_app(app)
    extensions.mail.init_app(app)
    Markdown(app)

    if app.config.get('SQLALCHEMY_DATABASE_URI'):
        configure_coverage(app)

    if app.config.get('LOQUSDB_SETTINGS'):
        # setup LoqusDB
        extensions.loqusdb.init_app(app)


def register_blueprints(app):
    """Register Flask blueprints."""
    app.register_blueprint(public.public_bp)
    app.register_blueprint(genes.genes_bp)
    app.register_blueprint(cases.cases_bp)
    app.register_blueprint(login.login_bp)
    app.register_blueprint(variants.variants_bp)
    app.register_blueprint(panels.panels_bp)
    app.register_blueprint(dashboard.dashboard_bp)
    app.register_blueprint(api.api_bp)
    app.register_blueprint(alignviewers.alignviewers_bp)
    app.register_blueprint(phenotypes.hpo_bp)
    app.register_blueprint(institutes.overview)


def register_filters(app):
    @app.template_filter()
    def human_decimal(number, ndigits=4):
        """Return a standard representation of a decimal number.

        Args:
            number (float): number to humanize
            ndigits (int, optional): max number of digits to round to

        Return:
            str: humanized string of the decimal number
        """
        min_number = 10 ** -ndigits

        if number is None:
            # NaN
            return '-'
        elif number == 0:
            # avoid confusion over what is rounded and what is actually 0
            return 0
        elif number < min_number:
            # make human readable and sane
            return "< {}".format(min_number)
        else:
            # round all other numbers
            return round(number, ndigits)

    @app.template_filter()
    def url_decode(string):
        """Decode a string with encoded hex values."""
        return unquote(string)


def configure_email_logging(app):
    """Setup logging of error/exceptions to email."""
    import logging
    from scout.log import TlsSMTPHandler

    mail_handler = TlsSMTPHandler(
        mailhost=app.config['MAIL_SERVER'],
        fromaddr=app.config['MAIL_USERNAME'],
        toaddrs=app.config['ADMINS'],
        subject="O_ops... {} failed!".format(app.name),
        credentials=(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
    )
    mail_handler.setLevel(logging.ERROR)
    mail_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]')
    )
    app.logger.addHandler(mail_handler)


def configure_coverage(app):
    """Setup coverage related extensions."""
    # setup chanjo report
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True if app.debug else False
    if chanjo_api:
        chanjo_api.init_app(app)
        configure_template_filters(app)
        # register chanjo report blueprint
        app.register_blueprint(report_bp, url_prefix='/reports')

    babel = Babel(app)

    @babel.localeselector
    def get_locale():
        """Determine locale to use for translations."""
        accept_languages = current_app.config.get('ACCEPT_LANGUAGES', ['en'])

        # first check request args
        session_language = request.args.get('lang')
        if session_language in accept_languages:
            current_app.logger.info("using session language: %s", session_language)
            return session_language

        # language can be forced in config
        user_language = current_app.config.get('REPORT_LANGUAGE')
        if user_language:
            return user_language

        # try to guess the language from the user accept header that
        # the browser transmits.  We support de/fr/en in this example.
        # The best match wins.
        return request.accept_languages.best_match(accept_languages)
