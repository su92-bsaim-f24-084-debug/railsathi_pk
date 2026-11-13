import os
from flask import Flask, render_template
from app.config import config_by_name, Config
from app.extensions import db, migrate, login_manager, csrf
from app.main import main_bp
from app.auth import auth_bp
from app.admin import admin_bp
import app.models  # Register domain models with metadata


def create_app(config_class=None) -> Flask:
    """
    Application Factory for RailSathi PK.
    
    :param config_class: Configuration class, configuration name string, or None.
    :return: Configured Flask application instance.
    """
    app = Flask(__name__)

    # Determine configuration class
    if config_class is None:
        env_mode = os.environ.get("FLASK_CONFIG", "default").lower()
        config_obj = config_by_name.get(env_mode, config_by_name["default"])
    elif isinstance(config_class, str):
        config_obj = config_by_name.get(config_class.lower(), config_by_name["default"])
    else:
        config_obj = config_class

    # If config_obj is a class, instantiate it to trigger validation checks (e.g., ProductionConfig SECRET_KEY check)
    if isinstance(config_obj, type):
        config_instance = config_obj()
        app.config.from_object(config_instance)
    else:
        app.config.from_object(config_obj)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=False)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # Register CLI Commands
    register_cli_commands(app)

    # Register Global Error Handlers
    register_error_handlers(app)

    return app


def register_cli_commands(app: Flask):
    """Registers custom Flask CLI commands."""
    import click

    @app.cli.command("seed")
    def seed_command():
        """Seed the database idempotently with initial reference data and demo railway network."""
        from app.seed import seed_all
        seed_all()
        click.echo("Seeding complete.")



def register_error_handlers(app: Flask):
    """Registers standard HTTP error handlers with Jinja2 template rendering."""

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", error=error), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html", error=error), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html", error=error), 404

    @app.errorhandler(500)
    def internal_server_error(error):
        return render_template("errors/500.html", error=error), 500

