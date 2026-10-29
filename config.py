import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
ADMIN_IDS = {int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip().isdigit()}
NIGHT_SECONDS = int(os.getenv('NIGHT_SECONDS', '60'))
DAY_SECONDS = int(os.getenv('DAY_SECONDS', '90'))
MIN_PLAYERS = int(os.getenv('MIN_PLAYERS', '5'))
MAX_PLAYERS = int(os.getenv('MAX_PLAYERS', '12'))
REQUIRED_CHANNELS = ('@miogptstudio', '@shady_garden')

# Render sets RENDER_EXTERNAL_URL automatically; WEB_APP_URL may override it.
WEB_APP_URL = os.getenv("WEB_APP_URL", os.getenv("RENDER_EXTERNAL_URL", "")).strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
