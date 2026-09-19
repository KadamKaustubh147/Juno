"""App-wide settings, read from the environment (.env in dev).

Note app/memory/semantic/vector_store.py still reads DATABASE_URL itself on
purpose -- the memory layer is meant to work standalone, without importing the app.
"""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
AICREDITS_API_KEY = os.environ["AICREDITS_API_KEY"]
