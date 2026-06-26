import os
from app import app
from database import init_db
from auth import init_auth_db

if not os.path.exists("demo.db"):
    init_db()

init_auth_db()

application = app