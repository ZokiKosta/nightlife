from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from database import db
from routes.home   import home_bp
from routes.events import events_bp
from routes.admin  import admin_bp
from utils.logger  import setup_logger
from utils.migrate import run_migrations
import os


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"]                     = os.environ.get("SECRET_KEY", "nocturn-dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"]        = "sqlite:///nightlife.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    app.register_blueprint(home_bp)
    app.register_blueprint(events_bp, url_prefix="/events")
    app.register_blueprint(admin_bp,  url_prefix="/admin")

    with app.app_context():
        db.create_all()
        run_migrations(db)   # widen image_url column if needed

    logger = setup_logger()
    logger.info("NOCTURN started")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)