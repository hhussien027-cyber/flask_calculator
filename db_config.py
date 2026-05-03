from flask_sqlalchemy import SQLAlchemy

LOCAL_DATABASE_URI = "mysql+pymysql://root:@localhost/calculator_db"

db = SQLAlchemy()


def configure_database(app):
    app.config["SQLALCHEMY_DATABASE_URI"] = LOCAL_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
