import os
from app import app
from database import init_db
from auth import init_auth_db

# init_db() drops tables — only run if demo.db is missing
if not os.path.exists("demo.db"):
    init_db()

init_auth_db()