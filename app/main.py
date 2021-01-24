from typing import Optional
from datetime import datetime


from fastapi import Depends, FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import models
from app.database.models import Event
from app.database.database import SessionLocal, engine, get_db
from app.routers import event

models.Base.metadata.create_all(bind=engine)


app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
app.include_router(event.router)



@app.get("/")
def home(request: Request):
    return templates.TemplateResponse('home.html',{
        "request": request,
        "message": "Hello, World!"
    })


@app.get("/profile")
def profile(request: Request):

    # Get relevant data from database
    upcouming_events = range(5)
    current_username = "Chuck Norris"

    return templates.TemplateResponse("profile.html", {
        "request": request,
        "username": current_username,
        "events": upcouming_events
    })


# @app.get("/profile/{user_id}/EditEvent", response_class=HTMLResponse)
# async def insert_info(request: Request) -> HTMLResponse:
#     """Get request and return an html File"""
#     return templates.TemplateResponse("editevent.html",{"request": request})


# @app.post("/profile/{user_id}/EditEvent") # this func is soupose to change with the PR of Ode and Efrat and it will be change
# def create_event(user_id: int, event_title: str = Form(None), location: Optional[str] = Form(None), from_date: Optional[datetime] = Form(...),
#                 to_date: Optional[datetime] = Form(...), link_vc: str = Form(None), content: str = Form(None),
#                  db = Depends(get_db)) -> dict:
#     """ required args - title, from_date, to_date, user_id, the 'from_date' need to be early from the 'to_date'.
#     check validation for the value, insert the new data to DB 
#     if the prosess success return True arg the event item, otherwith return False and the error msg """
#     success = False
#     error_msg = ""
#     new_event = ""
#     if event_title is None:
#         event_title = "No Title"
#     try:
#         if check_validation(from_date, to_date):
#             event_value = {'title': event_title, "location": location, "start_date": from_date, "end_date": to_date, "vc_link":link_vc, "content": content, 
#                 "owner_id": user_id}
#             new_event = add_event(event_value, db)
#             success = True
#         else:
#             error_msg = "Error, Your date is invalid"
#     except Exception as e:
#         error_msg = e
#     finally:
#         return {"success": success, "new_event": new_event, "error_msg": error_msg}

