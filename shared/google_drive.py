"""
Google Drive Integration

Access and process files from Google Drive without downloading them individually.
Supports both service account and OAuth authentication.
"""

import io
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import tempfile
import os

logger = logging.getLogger(__name__)


@dataclass
class DriveFile:
    """Represents a file in Google Drive."""
    id: str
    name: str
    mime_type: str
    size: int
    modified_time: str
    web_view_link: Optional[str] = None


class GoogleDriveService:
    """
    Service for accessing Google Drive files.
    
    Supports:
    - Service account authentication (recommended for server use)
    - OAuth authentication (for user-specific access)
    - Direct file streaming (no local download required)
    - Folder listing and file enumeration
    """
    
    def __init__(self, credentials_path: Optional[str] = None, use_service_account: bool = True):
        """
        Initialize Google Drive service.
        
        Args:
            credentials_path: Path to service account JSON or OAuth credentials
            use_service_account: If True, use service account; if False, use OAuth
        """
        self.credentials_path = credentials_path
        self.use_service_account = use_service_account
        self._service = None
        self._drive_service = None
    
    def _get_service(self):
        """Get authenticated Google Drive service."""
        if self._drive_service:
            return self._drive_service
        
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload
            from googleapiclient.errors import HttpError
        except ImportError:
            raise ImportError(
                "Google API client not installed. Install with: "
                "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
            )
        
        if self.use_service_account:
            if not self.credentials_path:
                raise ValueError("Service account credentials path required")
            
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            import pickle
            
            SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
            creds = None
            
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_path:
                        raise ValueError("OAuth credentials path required")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            
            credentials = creds
        
        self._drive_service = build('drive', 'v3', credentials=credentials)
        return self._drive_service
    
    def list_folder_files(
        self, 
        folder_id: str, 
        file_types: Optional[List[str]] = None,
        recursive: bool = False
    ) -> List[DriveFile]:
        """
        List all files in a Google Drive folder.
        
        Args:
            folder_id: Google Drive folder ID (from URL: .../folders/FOLDER_ID)
            file_types: Optional list of MIME types to filter (e.g., ['application/pdf'])
            recursive: If True, include files in subfolders
        
        Returns:
            List of DriveFile objects
        """
        service = self._get_service()
        files = []
        page_token = None
        
        query = f"'{folder_id}' in parents and trashed=false"
        if file_types:
            mime_types = " or ".join([f"mimeType='{mt}'" for mt in file_types])
            query += f" and ({mime_types})"
        
        while True:
            try:
                results = service.files().list(
                    q=query,
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, webViewLink)",
                    pageToken=page_token
                ).execute()
                
                items = results.get('files', [])
                
                for item in items:
                    if item.get('mimeType') == 'application/vnd.google-apps.folder' and recursive:
                        subfolder_files = self.list_folder_files(
                            item['id'], 
                            file_types=file_types, 
                            recursive=True
                        )
                        files.extend(subfolder_files)
                    else:
                        files.append(DriveFile(
                            id=item['id'],
                            name=item['name'],
                            mime_type=item.get('mimeType', ''),
                            size=int(item.get('size', 0)),
                            modified_time=item.get('modifiedTime', ''),
                            web_view_link=item.get('webViewLink')
                        ))
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            except Exception as e:
                logger.error(f"Error listing folder files: {e}")
                break
        
        logger.info(f"Found {len(files)} files in folder {folder_id}")
        return files
    
    def download_file_to_stream(self, file_id: str) -> Tuple[io.BytesIO, str, str]:
        """
        Download a file from Google Drive to a BytesIO stream.
        
        Args:
            file_id: Google Drive file ID
        
        Returns:
            Tuple of (BytesIO stream, filename, mime_type)
        """
        service = self._get_service()
        
        try:
            file_metadata = service.files().get(fileId=file_id).execute()
            filename = file_metadata.get('name', 'unknown')
            mime_type = file_metadata.get('mimeType', '')
            
            if 'google-apps' in mime_type:
                request = service.files().export_media(
                    fileId=file_id,
                    mimeType='application/pdf' if 'document' in mime_type else 'application/pdf'
                )
            else:
                request = service.files().get_media(fileId=file_id)
            
            file_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(file_stream, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
            
            file_stream.seek(0)
            return file_stream, filename, mime_type
        
        except Exception as e:
            logger.error(f"Error downloading file {file_id}: {e}")
            raise
    
    def download_file_to_path(
        self, 
        file_id: str, 
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Download a file from Google Drive to a local path.
        
        Args:
            file_id: Google Drive file ID
            output_path: Optional output path (creates temp file if not provided)
        
        Returns:
            Path to downloaded file
        """
        file_stream, filename, mime_type = self.download_file_to_stream(file_id)
        
        if not output_path:
            suffix = Path(filename).suffix or '.pdf'
            output_path = Path(tempfile.mktemp(suffix=suffix))
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'wb') as f:
            f.write(file_stream.read())
        
        logger.info(f"Downloaded {filename} to {output_path}")
        return output_path
    
    def get_file_by_name(
        self, 
        folder_id: str, 
        filename: str
    ) -> Optional[DriveFile]:
        """
        Find a file by name in a folder.
        
        Args:
            folder_id: Google Drive folder ID
            filename: Name of the file to find
        
        Returns:
            DriveFile if found, None otherwise
        """
        files = self.list_folder_files(folder_id)
        for file in files:
            if file.name == filename:
                return file
        return None
    
    def extract_folder_id_from_url(self, url: str) -> str:
        """
        Extract folder ID from Google Drive URL.
        
        Supports formats:
        - https://drive.google.com/drive/folders/FOLDER_ID
        - https://drive.google.com/drive/u/0/folders/FOLDER_ID
        - FOLDER_ID (if already just the ID)
        
        Args:
            url: Google Drive folder URL or ID
        
        Returns:
            Folder ID
        """
        if '/' not in url:
            return url
        
        parts = url.split('/')
        folder_id = None
        
        for i, part in enumerate(parts):
            if part == 'folders' and i + 1 < len(parts):
                folder_id = parts[i + 1].split('?')[0].split('#')[0]
                break
        
        if not folder_id:
            raise ValueError(f"Could not extract folder ID from URL: {url}")
        
        return folder_id

