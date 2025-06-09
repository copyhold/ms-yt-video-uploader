# youtube_uploader.py
import os
import pickle # Using pickle for simplicity, consider more secure storage for production
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import threading # For cancel_event

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'
CLIENT_SECRETS_FILE = 'client_secret.json' # Make sure this file is in the same directory
TOKEN_FILE = 'token.json' # Stores the user's access and refresh tokens

def get_authenticated_service():
    """Logs in the user or loads existing credentials and returns a YouTube service object."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Error refreshing token: {e}")
                # If refresh fails, force re-authentication
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                creds = None # Ensure re-authentication path is taken
        
        if not creds: # Either no token file or refresh failed
            if not os.path.exists(CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"'{CLIENT_SECRETS_FILE}' not found. "
                    "Please download it from Google Cloud Console and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            # Run local server for auth, will open browser
            creds = flow.run_local_server(port=0) 
        
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    if not creds:
        raise Exception("Failed to obtain YouTube API credentials.")

    return build(API_SERVICE_NAME, API_VERSION, credentials=creds)

def upload_video(service, file_path, title, description, category_id="22",
                 privacy_status="private", tags=None, cancel_event: threading.Event = None): # Added cancel_event
    """Uploads a video to YouTube. Checks for cancellation."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Video file not found: {file_path}")

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags if tags else [],
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': privacy_status,
            'selfDeclaredMadeForKids': False # Adjust if needed
        }
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)

    print(f"Uploading '{title}' to YouTube...")
    request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    upload_status_code = "SUCCESS" # Default status

    while response is None:
        if cancel_event and cancel_event.is_set():
            print(f"Upload of '{title}' cancelled by user.")
            # For resumable uploads, stopping here is usually enough.
            # The incomplete upload might remain in YouTube Studio drafts.
            upload_status_code = "CANCELLED"
            break # Exit the loop

        try:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}% for '{title}'")
        except Exception as e:
            print(f"An error occurred during upload of '{title}': {e}")
            upload_status_code = "ERROR"
            break # Exit the loop
    
    if upload_status_code == "SUCCESS" and response:
        print(f"Upload complete for '{title}'. Video ID: {response.get('id')}")
        return response # Return the full response object
    elif upload_status_code == "CANCELLED":
        return "CANCELLED" # Special string to indicate cancellation
    else: # ERROR or other unexpected state
        return None # Indicate failure or incomplete upload due to error