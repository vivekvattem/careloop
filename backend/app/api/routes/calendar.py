from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import RedirectResponse
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies.auth import require_roles
from app.db.session import get_db
from app.models.calendar import GoogleCalendarConnection
from app.models.appointment import Appointment
from app.models.user import User,UserRole
from app.services.calendar import connect_url,disconnect,finish_callback
from app.services.calendar import enqueue_sync
router=APIRouter(prefix="/integrations/google-calendar",tags=["calendar"])
@router.get('/status')
def status(user:User=Depends(require_roles(UserRole.PATIENT)),db:Session=Depends(get_db)):
 row=db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==user.id)); return {"status":row.status if row else "disconnected","calendar_id":row.calendar_id if row else None}
@router.post('/connect')
def connect(user:User=Depends(require_roles(UserRole.PATIENT)),db:Session=Depends(get_db)):
 try:return {"authorization_url":connect_url(db,user.id)}
 except RuntimeError as exc:raise HTTPException(503,str(exc))
@router.post('/disconnect')
def do_disconnect(user:User=Depends(require_roles(UserRole.PATIENT)),db:Session=Depends(get_db)): disconnect(db,user.id);return {"status":"disconnected"}
@router.get('/callback')
def callback(state:str|None=Query(None),code:str|None=Query(None),error:str|None=Query(None),db:Session=Depends(get_db)):
 try:
  if error: raise RuntimeError("Google authorization was not completed")
  destination=finish_callback(db,state or "",code or "")
  return RedirectResponse(f"http://localhost:5173{destination}?calendar=connected")
 except RuntimeError: return RedirectResponse("http://localhost:5173/patient?calendar=failed")
@router.post('/sync/{appointment_id}')
def sync(appointment_id:UUID,user:User=Depends(require_roles(UserRole.PATIENT)),db:Session=Depends(get_db)):
 appointment=db.get(Appointment,appointment_id)
 if not appointment or appointment.patient_user_id!=user.id:raise HTTPException(404,"Appointment not found")
 if not db.scalar(select(GoogleCalendarConnection).where(GoogleCalendarConnection.user_id==user.id,GoogleCalendarConnection.status=="connected")):raise HTTPException(409,"Google Calendar is not connected")
 job=enqueue_sync(db,appointment,user.id);db.commit();return {"job_id":str(job.id),"status":job.status}
