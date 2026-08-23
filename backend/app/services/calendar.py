import hashlib, secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from cryptography.fernet import Fernet, InvalidToken
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.calendar import GoogleOAuthState, GoogleCalendarConnection, CalendarConnectionStatus, CalendarSyncJob, CalendarSyncStatus, CalendarOperation, AppointmentCalendarMapping
from app.models.appointment import Appointment, AppointmentStatus

def cipher() -> Fernet:
    if not settings.google_token_encryption_key: raise RuntimeError("Google token encryption is not configured")
    return Fernet(settings.google_token_encryption_key.encode())
def encrypt(value: str) -> str: return cipher().encrypt(value.encode()).decode()
def decrypt(value: str) -> str:
    try: return cipher().decrypt(value.encode()).decode()
    except InvalidToken as exc: raise RuntimeError("Stored Google token cannot be decrypted") from exc
def connect_url(db: Session, user_id, redirect_destination="/patient") -> str:
    if not settings.google_client_id or not settings.google_client_secret: raise RuntimeError("Google Calendar is not configured")
    state=secrets.token_urlsafe(32); now=datetime.now(timezone.utc); db.add(GoogleOAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(),user_id=user_id,redirect_destination=redirect_destination,expires_at=now+timedelta(minutes=10),created_at=now)); db.commit()
    return "https://accounts.google.com/o/oauth2/v2/auth?"+urlencode({"client_id":settings.google_client_id,"redirect_uri":settings.google_redirect_uri,"response_type":"code","scope":settings.google_calendar_scopes,"state":state,"access_type":"offline","prompt":"consent"})
def consume_state(db: Session,state: str):
    if not state or len(state) < 32: raise RuntimeError("Invalid or expired OAuth state")
    row=db.scalar(select(GoogleOAuthState).where(GoogleOAuthState.state_hash==hashlib.sha256(state.encode()).hexdigest()).with_for_update())
    expiry = row.expires_at.replace(tzinfo=timezone.utc) if row and row.expires_at.tzinfo is None else (row.expires_at if row else None)
    if not row or row.consumed_at or expiry < datetime.now(timezone.utc): raise RuntimeError("Invalid or expired OAuth state")
    row.consumed_at=datetime.now(timezone.utc); db.commit(); return row
def disconnect(db: Session,user_id):
    row=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==user_id))
    if row:
     row.access_token_encrypted=""; row.refresh_token_encrypted=None; row.status=CalendarConnectionStatus.DISCONNECTED; row.disconnected_at=datetime.now(timezone.utc)
     for job in db.scalars(select(CalendarSyncJob).where(CalendarSyncJob.user_id==user_id,CalendarSyncJob.status.in_([CalendarSyncStatus.PENDING,CalendarSyncStatus.RETRY_SCHEDULED]))): job.status=CalendarSyncStatus.CANCELLED
     db.commit()

def enqueue_sync(db: Session, appointment: Appointment, user_id, operation=None):
 connection=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==user_id,GoogleCalendarConnection.status==CalendarConnectionStatus.CONNECTED))
 if not connection:return None
 mapping=db.scalar(select(AppointmentCalendarMapping).where(AppointmentCalendarMapping.appointment_id==appointment.id,AppointmentCalendarMapping.user_id==user_id,AppointmentCalendarMapping.calendar_id==connection.calendar_id))
 op=operation or (CalendarOperation.DELETE if appointment.status==AppointmentStatus.CANCELLED else (CalendarOperation.UPDATE if mapping else CalendarOperation.CREATE))
 key=f"calendar:{appointment.id}:{user_id}:{op.value}:{appointment.updated_at.isoformat()}"
 existing=db.scalar(select(CalendarSyncJob).where(CalendarSyncJob.idempotency_key==key))
 if existing:return existing
 job=CalendarSyncJob(appointment_id=appointment.id,user_id=user_id,operation=op,idempotency_key=key,status=CalendarSyncStatus.PENDING,attempt_count=0,next_attempt_at=datetime.now(timezone.utc));db.add(job);return job

class GoogleProviderError(Exception):
 def __init__(self, category, retryable=False): self.category=category;self.retryable=retryable

class GoogleProvider:
 def __init__(self, transport=None, timeout=8): self.transport=transport;self.timeout=timeout
 def _request(self, method, url, **kwargs):
  try:
   with httpx.Client(transport=self.transport,timeout=self.timeout) as client:r=client.request(method,url,**kwargs)
  except (httpx.TimeoutException,httpx.ConnectError) as exc:raise GoogleProviderError("connection",True) from exc
  if r.status_code in (429,) or r.status_code>=500:raise GoogleProviderError("provider_unavailable",True)
  if r.status_code in (401,403) or (r.status_code==400 and "invalid_grant" in r.text):raise GoogleProviderError("reauthorization_required")
  if r.status_code>=400:raise GoogleProviderError("provider_rejected")
  return r
 def exchange_code(self, code: str) -> dict:
  return self._request("POST","https://oauth2.googleapis.com/token",data={"code":code,"client_id":settings.google_client_id,"client_secret":settings.google_client_secret,"redirect_uri":settings.google_redirect_uri,"grant_type":"authorization_code"}).json()
 def refresh(self, db, connection):
  if not connection.refresh_token_encrypted:raise GoogleProviderError("reauthorization_required")
  data=self._request("POST","https://oauth2.googleapis.com/token",data={"refresh_token":decrypt(connection.refresh_token_encrypted),"client_id":settings.google_client_id,"client_secret":settings.google_client_secret,"grant_type":"refresh_token"}).json()
  if not data.get("access_token"):raise GoogleProviderError("reauthorization_required")
  connection.access_token_encrypted=encrypt(data["access_token"]);connection.token_expiry=datetime.now(timezone.utc)+timedelta(seconds=int(data.get("expires_in",3600)))
  if data.get("refresh_token"):connection.refresh_token_encrypted=encrypt(data["refresh_token"])
  if data.get("scope"):connection.scopes=data["scope"]
  db.commit();return decrypt(connection.access_token_encrypted)
 def _event(self, connection, payload):
  allowed={"summary","start","end","timezone","consultation_mode","careloop_appointment_reference"}
  if set(payload)-allowed:raise GoogleProviderError("invalid_payload")
  body={"summary":payload["summary"],"start":{"dateTime":payload["start"],"timeZone":payload["timezone"]},"end":{"dateTime":payload["end"],"timeZone":payload["timezone"]},"description":f"CareLoop appointment reference: {payload['careloop_appointment_reference']}"}
  return body,{"Authorization":f"Bearer {decrypt(connection.access_token_encrypted)}"}
 def create_event(self,connection,payload):
  body,h=self._event(connection,payload);r=self._request("POST",f"https://www.googleapis.com/calendar/v3/calendars/{connection.calendar_id or 'primary'}/events",headers=h,json=body);return {"event_id":r.json()["id"],"calendar_id":connection.calendar_id or "primary"}
 def update_event(self,connection,event_id,payload):
  if not event_id:raise GoogleProviderError("invalid_payload")
  body,h=self._event(connection,payload);r=self._request("PUT",f"https://www.googleapis.com/calendar/v3/calendars/{connection.calendar_id or 'primary'}/events/{event_id}",headers=h,json=body);return {"event_id":r.json().get("id",event_id),"calendar_id":connection.calendar_id or "primary"}
 def delete_event(self,connection,event_id):
  if not event_id:return {"deleted":True}
  try:self._request("DELETE",f"https://www.googleapis.com/calendar/v3/calendars/{connection.calendar_id or 'primary'}/events/{event_id}",headers={"Authorization":f"Bearer {decrypt(connection.access_token_encrypted)}"})
  except GoogleProviderError as exc:
   if exc.category=="provider_rejected":return {"deleted":True}
   raise
  return {"deleted":True}

def finish_callback(db: Session,state: str,code: str,provider=None):
 row=consume_state(db,state)
 if not code: raise RuntimeError("Google authorization was not completed")
 # State is consumed before exchange: retries require a fresh OAuth flow, preventing code/state replay.
 token=(provider or GoogleProvider()).exchange_code(code)
 access=token.get("access_token")
 if not access: raise RuntimeError("Google authorization exchange failed")
 connection=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==row.user_id).with_for_update())
 values={"access_token_encrypted":encrypt(access),"refresh_token_encrypted":encrypt(token["refresh_token"]) if token.get("refresh_token") else (connection.refresh_token_encrypted if connection else None),"token_expiry":datetime.now(timezone.utc)+timedelta(seconds=int(token.get("expires_in",3600))),"scopes":token.get("scope",settings.google_calendar_scopes),"calendar_id":"primary","status":CalendarConnectionStatus.CONNECTED,"disconnected_at":None}
 if connection:
  for key,value in values.items():setattr(connection,key,value)
 else: connection=GoogleCalendarConnection(user_id=row.user_id,**values);db.add(connection)
 db.commit();return row.redirect_destination
