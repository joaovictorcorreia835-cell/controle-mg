from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
db = SQLAlchemy()
login = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
