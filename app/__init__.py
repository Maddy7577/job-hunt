import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

db = SQLAlchemy()


def create_app():
    app = Flask(__name__, static_folder="static", static_url_path="/static")

    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///jobhunt.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "uploads")
    app.config["MAX_RESULTS_DEFAULT"] = int(os.getenv("MAX_RESULTS_DEFAULT", "50"))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    CORS(app)

    from app.routes.resume import resume_bp
    from app.routes.search import search_bp
    from app.routes.jobs import jobs_bp

    app.register_blueprint(resume_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(jobs_bp)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    return app
