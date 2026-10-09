import os
from dotenv import load_dotenv
load_dotenv()
class Config:
    DEBUG = False
    TESTING = False
    IS_PRODUCTION = os.getenv("RENDER", "").lower() == "true"
    ALLOW_MANUAL_PARTS = os.getenv("ALLOW_MANUAL_PARTS", "false").lower() == "true"
    PARTS_ON_DEMAND = os.getenv("PARTS_ON_DEMAND", "false").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///oficina.db").replace("postgres://", "postgresql+psycopg://", 1).replace("postgresql://", "postgresql+psycopg://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER")
