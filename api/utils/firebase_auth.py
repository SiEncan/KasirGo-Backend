
import os
import json
import firebase_admin
from firebase_admin import credentials, auth
from django.conf import settings

# Initialize Firebase App
# Ensure 'serviceAccountKey.json' is in your project root or specified path
LOG_TAG = "[FirebaseAuth]"

def initialize_firebase():
  try:
    if not firebase_admin._apps:
      # 1. Try Environment Variable (For Vercel)
      firebase_json = os.getenv('FIREBASE_SERVICE_ACCOUNT')
      
      if firebase_json:
          try:
              cred_dict = json.loads(firebase_json)
              cred = credentials.Certificate(cred_dict)
              firebase_admin.initialize_app(cred)
              print(f"{LOG_TAG} Initialized successfully using Environment Variable.")
              return
          except Exception as e:
              print(f"{LOG_TAG} Failed to load env var content: {e}")

      # 2. Try Local File
      base_dir = settings.BASE_DIR
      cred_path = os.path.join(base_dir, 'serviceAccountKey.json')
      
      if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print(f"{LOG_TAG} Initialized successfully using {cred_path}")
      else:
        print(f"{LOG_TAG} Warning: serviceAccountKey.json not found. Set FIREBASE_SERVICE_ACCOUNT env var or add file.")
  except Exception as e:
    print(f"{LOG_TAG} Initialization error: {str(e)}")
    import traceback
    traceback.print_exc()

def create_custom_token(user_id, additional_claims=None):
  """
  Mint a custom token for the given user_id.
  """
  initialize_firebase()
  try:
    # User ID must be a string
    uid = str(user_id)
    custom_token = auth.create_custom_token(uid, additional_claims)
    # In newer python SDK, create_custom_token returns bytes, we decode to string
    if isinstance(custom_token, bytes):
      return custom_token.decode('utf-8')
    return custom_token
  except Exception as e:
    print(f"{LOG_TAG} Error minting token: {str(e)}")
    return None